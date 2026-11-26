package tw.vera.nexus;
import android.Manifest;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.webkit.*;
import android.widget.Toast;

public class MainActivity extends Activity {
 private WebView web;
 private PermissionRequest pending;
 private boolean requestingMic=false;
 private volatile String pendingReminder="";
 private void captureReminder(Intent i){
  if(i!=null&&ReminderReceiver.OPEN.equals(i.getAction())){
   String k=i.getStringExtra("reminder_kind");
   if("daily".equals(k)||"test".equals(k))pendingReminder=k;
   i.setAction(Intent.ACTION_MAIN);i.removeExtra("reminder_kind");
  }
 }
 @Override protected void onNewIntent(Intent i){super.onNewIntent(i);setIntent(i);captureReminder(i);if(web!=null)web.evaluateJavascript("window.veraReadReminder && window.veraReadReminder()",null);}
 private String reminderState(){
  try{android.content.SharedPreferences p=ReminderReceiver.prefs(this);org.json.JSONObject j=new org.json.JSONObject();
   j.put("enabled",p.getBoolean("enabled",false));j.put("hour",p.getInt("hour",9));j.put("minute",p.getInt("minute",0));j.put("next",p.getLong("next",0));j.put("notifications",ReminderReceiver.notifyAllowed(this));j.put("exact",ReminderReceiver.exactAllowed(this));return j.toString();
  }catch(Exception e){return "{}";}
 }
 private static final String HOST="publish-task.onrender.com";
 private boolean allowed(Uri u){return u!=null && "https".equals(u.getScheme()) && HOST.equals(u.getHost()) && (u.getPort()==-1 || u.getPort()==443);}
 private static final String LOGIN_KEY="vera_nexus_token_v1";
 private SecretKey loginKey(boolean create) throws Exception{
  KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
  if(ks.containsAlias(LOGIN_KEY))return (SecretKey)ks.getKey(LOGIN_KEY,null);
  if(!create)return null;
  KeyGenerator gen=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
  gen.init(new KeyGenParameterSpec.Builder(LOGIN_KEY,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
    .setKeySize(256).setRandomizedEncryptionRequired(true).build());
  return gen.generateKey();
 }
 private synchronized boolean saveLogin(String token){
  if(token==null||token.length()<16||token.length()>4096)return false;
  try{
   Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,loginKey(true));
   byte[] encrypted=c.doFinal(token.getBytes(StandardCharsets.UTF_8));
   return getSharedPreferences("vera_secure_login",MODE_PRIVATE).edit()
     .putString("iv",Base64.encodeToString(c.getIV(),Base64.NO_WRAP))
     .putString("ciphertext",Base64.encodeToString(encrypted,Base64.NO_WRAP)).commit();
  }catch(Exception e){return false;}
 }
 private synchronized String loadLogin(){
  try{
   android.content.SharedPreferences p=getSharedPreferences("vera_secure_login",MODE_PRIVATE);
   String iv=p.getString("iv",null),enc=p.getString("ciphertext",null);
   if(iv==null||enc==null)return "";
   SecretKey key=loginKey(false);if(key==null)return "";
   Cipher c=Cipher.getInstance("AES/GCM/NoPadding");
   c.init(Cipher.DECRYPT_MODE,key,new GCMParameterSpec(128,Base64.decode(iv,Base64.NO_WRAP)));
   return new String(c.doFinal(Base64.decode(enc,Base64.NO_WRAP)),StandardCharsets.UTF_8);
  }catch(Exception e){return "";}
 }
 private synchronized boolean clearLogin(){
  boolean ok=getSharedPreferences("vera_secure_login",MODE_PRIVATE).edit().clear().commit();
  try{KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);ks.deleteEntry(LOGIN_KEY);return ok;}catch(Exception e){return false;}
 }
 private boolean micGranted(){return checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED;}
 private void requestMic(){
  if(micGranted() || requestingMic || isFinishing()) return;
  requestingMic=true;
  requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},41);
 }
 @Override public void onCreate(Bundle b){
  super.onCreate(b);captureReminder(getIntent());ReminderReceiver.channel(this);
  getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
  setVolumeControlStream(AudioManager.STREAM_VOICE_CALL);
  web=new WebView(this); setContentView(web);
  if(Build.VERSION.SDK_INT>=30){
   web.setOnApplyWindowInsetsListener((v,insets)->{
    android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
    v.setPadding(bars.left,bars.top,bars.right,bars.bottom);
    return insets;
   });
   web.requestApplyInsets();
  }
  WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);
  s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMediaPlaybackRequiresUserGesture(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
  web.setWebViewClient(new WebViewClient(){
   @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){return !allowed(r.getUrl());}
   @Override public void onReceivedError(WebView v,WebResourceRequest r,WebResourceError e){if(r.isForMainFrame())Toast.makeText(MainActivity.this,"無法連線 VERA，請確認網路後重新開啟",Toast.LENGTH_LONG).show();}
  });
  web.setWebChromeClient(new WebChromeClient(){
   @Override public void onPermissionRequest(PermissionRequest r){runOnUiThread(()->{
    if(isFinishing() || !allowed(r.getOrigin()) || !java.util.Arrays.asList(r.getResources()).contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)){r.deny();return;}
    if(micGranted()){r.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});return;}
    if(pending!=null){pending.deny();}
    pending=r;requestMic();
   });}
   @Override public void onPermissionRequestCanceled(PermissionRequest r){if(pending==r)pending=null;}
  });
  web.addJavascriptInterface(new Object(){
   @JavascriptInterface public void share(String t){if(t==null||t.length()>100000)return;runOnUiThread(()->{Intent i=new Intent(Intent.ACTION_SEND);i.setType("text/plain");i.putExtra(Intent.EXTRA_TEXT,t);startActivity(Intent.createChooser(i,"分享 VERA 摘要"));});}
   @JavascriptInterface public boolean saveVerifiedLogin(String token){return saveLogin(token);}
   @JavascriptInterface public String loadVerifiedLogin(){return loadLogin();}
   @JavascriptInterface public boolean clearVerifiedLogin(){return clearLogin();}
   @JavascriptInterface public String reminderStatus(){return reminderState();}
   @JavascriptInterface public boolean scheduleDaily(int h,int m){return ReminderReceiver.configure(MainActivity.this,h,m);}
   @JavascriptInterface public boolean scheduleTest(){return ReminderReceiver.schedule(MainActivity.this,true,System.currentTimeMillis()+60000L);}
   @JavascriptInterface public void cancelDailyReminder(){ReminderReceiver.cancelDaily(MainActivity.this);}
   @JavascriptInterface public void cancelAllReminders(){ReminderReceiver.cancelAll(MainActivity.this);pendingReminder="";}
   @JavascriptInterface public String takeReminder(){String k=pendingReminder;pendingReminder="";return k;}
   @JavascriptInterface public void requestNotifications(){runOnUiThread(()->{
    if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},42);
    else {Intent i=new Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName());startActivity(i);}
   });}
   @JavascriptInterface public void requestExactAlarm(){runOnUiThread(()->{
    if(Build.VERSION.SDK_INT>=31&&!ReminderReceiver.exactAllowed(MainActivity.this)){
      try{startActivity(new Intent(android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,Uri.parse("package:"+getPackageName())));}catch(Exception e){Toast.makeText(MainActivity.this,"請在系統設定允許鬧鐘與提醒",Toast.LENGTH_LONG).show();}
    }
   });}
   @JavascriptInterface public boolean hasMicPermission(){return micGranted();}
   @JavascriptInterface public void askMicPermission(){runOnUiThread(()->requestMic());}
  },"VeraAndroid");
  web.loadUrl("https://"+HOST+"/app");
  // Ask Android first, outside the asynchronous WebRTC capture request.
  if(!micGranted())web.postDelayed(()->{if(!isFinishing() && !isDestroyed())requestMic();},350);
 }
 @Override public void onRequestPermissionsResult(int r,String[] p,int[] g){
  super.onRequestPermissionsResult(r,p,g);
  if(r==42){if(web!=null)web.evaluateJavascript("window.veraRefreshReminder && window.veraRefreshReminder()",null);return;}
  if(r!=41)return;
  requestingMic=false;
  if(pending!=null){PermissionRequest req=pending;pending=null;
   if(micGranted())req.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});else req.deny();}
  if(web!=null)web.evaluateJavascript("window.veraPermissionChanged && window.veraPermissionChanged("+(micGranted()?"true":"false")+")",null);
 }
 @Override protected void onResume(){super.onResume();if(web!=null)web.evaluateJavascript("window.veraRefreshReminder && window.veraRefreshReminder(); window.veraReadReminder && window.veraReadReminder()",null);}
 @Override protected void onStop(){super.onStop();if(web!=null&&!requestingMic)web.evaluateJavascript("window.veraBackground && window.veraBackground()",null);}
 @Override protected void onDestroy(){if(pending!=null){pending.deny();pending=null;}if(web!=null){web.removeJavascriptInterface("VeraAndroid");web.destroy();web=null;}super.onDestroy();}
}
