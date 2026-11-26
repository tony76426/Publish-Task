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
 private String pendingBackup=null;
 private static final int SAVE_BACKUP=43,OPEN_BACKUP=44;
 private void captureReminder(Intent i){
  if(i!=null&&ReminderReceiver.OPEN.equals(i.getAction())){
   String k=i.getStringExtra("reminder_kind");
   if(k!=null&&("daily".equals(k)||"test".equals(k)||"remote".equals(k)||"remote-test".equals(k)||k.matches("task:[A-Za-z0-9-]{1,80}"))){String expected=ReminderReceiver.prefs(this).getString("acceptNonce","");String got=i.getStringExtra("accept_nonce");boolean accepted=!expected.isEmpty()&&expected.equals(got);String event=accepted?ReminderReceiver.prefs(this).getString("acceptEvent",""):"";if(accepted)ReminderReceiver.prefs(this).edit().remove("acceptNonce").remove("acceptEvent").commit();pendingReminder=accepted&&!event.isEmpty()?"accepted:cloud:"+event+":"+k:(accepted?"accepted:":"")+k;}
   i.setAction(Intent.ACTION_MAIN);i.removeExtra("reminder_kind");i.removeExtra("accept_nonce");
  }
 }
 @Override protected void onNewIntent(Intent i){super.onNewIntent(i);setIntent(i);captureReminder(i);if(web!=null)web.evaluateJavascript("window.veraReadReminder && window.veraReadReminder()",null);}
 private String reminderState(){
  try{android.content.SharedPreferences p=ReminderReceiver.prefs(this);org.json.JSONObject j=new org.json.JSONObject();
   j.put("enabled",p.getBoolean("enabled",false));j.put("hour",p.getInt("hour",9));j.put("minute",p.getInt("minute",0));j.put("next",p.getLong("next",0));j.put("notifications",ReminderReceiver.notifyAllowed(this));j.put("exact",ReminderReceiver.exactAllowed(this));j.put("fullAllowed",ReminderReceiver.fullAllowed(this));j.put("fullscreen",p.getBoolean("fullscreen",false));j.put("interval",p.getInt("interval",0));j.put("customTimes",new org.json.JSONArray(p.getString("customTimes","[]")));j.put("from",p.getInt("from",0));j.put("to",p.getInt("to",0));j.put("quiet",p.getBoolean("quiet",false));j.put("quietFrom",p.getInt("quietFrom",1320));j.put("quietTo",p.getInt("quietTo",420));j.put("retry",p.getBoolean("retry",false));j.put("tone",p.getString("tone","ring"));j.put("firedTasks",p.getString("firedTasks",""));j.put("log",ReminderReceiver.log(this));return j.toString();
  }catch(Exception e){return "{}";}
 }
 private static final String HOST="publish-task.onrender.com";
 private boolean allowed(Uri u){return u!=null && "https".equals(u.getScheme()) && HOST.equals(u.getHost()) && (u.getPort()==-1 || u.getPort()==443);}
 private static final String LOGIN_KEY="vera_nexus_token_v1";
 private static SecretKey loginKey(boolean create) throws Exception{
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
 static String loadLogin(android.content.Context context){
  try{
   android.content.SharedPreferences p=context.getSharedPreferences("vera_secure_login",MODE_PRIVATE);
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
   @JavascriptInterface public boolean saveVerifiedLogin(String token){boolean saved=saveLogin(token);if(saved)PushEnrollment.refresh(MainActivity.this);return saved;}
   @JavascriptInterface public String loadVerifiedLogin(){return loadLogin(MainActivity.this);}
   @JavascriptInterface public boolean clearVerifiedLogin(){
    boolean revoked=PushEnrollment.disable(MainActivity.this,loadLogin(MainActivity.this),false);
    return clearLogin()&&revoked;
   }
   @JavascriptInterface public void testPush(){runOnUiThread(()->PushEnrollment.enable(MainActivity.this,true));}
   @JavascriptInterface public void enableCloudPush(){runOnUiThread(()->PushEnrollment.enable(MainActivity.this,false));}
   @JavascriptInterface public String cloudDevice(){return PushEnrollment.localState(MainActivity.this);}
   @JavascriptInterface public void openVeraUpdate(String link){
    if(link==null||!link.matches("https://github\\.com/tony76426/Publish-Task/releases/download/vera-nexus-v[0-9.]+-fcm-[0-9]+-r[0-9]+/VERA-Nexus\\.apk"))return;
    runOnUiThread(()->{try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(link)));}catch(android.content.ActivityNotFoundException ignored){Toast.makeText(MainActivity.this,"無法開啟 APK 下載",Toast.LENGTH_LONG).show();}});
   }
   @JavascriptInterface public void disablePush(){runOnUiThread(()->{
    if(!PushEnrollment.disable(MainActivity.this,loadLogin(MainActivity.this),true))
     Toast.makeText(MainActivity.this,"無法儲存推播停用設定",Toast.LENGTH_LONG).show();
   });}
   @JavascriptInterface public String reminderStatus(){return reminderState();}
   @JavascriptInterface public int apkVersion(){return 9;}
   @JavascriptInterface public void setInCall(boolean on){ReminderReceiver.inCall=on;}
   @JavascriptInterface public void exportBackup(String data){if(data==null||data.length()>3000000)return;runOnUiThread(()->{pendingBackup=data;try{Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/json").putExtra(Intent.EXTRA_TITLE,"VERA-backup.json");startActivityForResult(i,SAVE_BACKUP);}catch(Exception e){pendingBackup=null;Toast.makeText(MainActivity.this,"無法開啟備份儲存器",Toast.LENGTH_LONG).show();}});}
   @JavascriptInterface public void importBackup(){runOnUiThread(()->{try{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/json");startActivityForResult(i,OPEN_BACKUP);}catch(Exception e){Toast.makeText(MainActivity.this,"無法開啟備份檔案",Toast.LENGTH_LONG).show();}});}
   @JavascriptInterface public boolean configureCalls(String raw){return ReminderReceiver.configureOptions(MainActivity.this,raw);}
   @JavascriptInterface public boolean syncTaskReminders(String raw){return ReminderReceiver.syncTasks(MainActivity.this,raw);}
   @JavascriptInterface public void clearCallLog(){ReminderReceiver.prefs(MainActivity.this).edit().remove("callLog").apply();}
   @JavascriptInterface public void requestFullscreen(){runOnUiThread(()->{if(Build.VERSION.SDK_INT>=34&&!ReminderReceiver.fullAllowed(MainActivity.this)){try{startActivity(new Intent(android.provider.Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT,Uri.parse("package:"+getPackageName())));}catch(Exception e){Toast.makeText(MainActivity.this,"請於系統設定檢查全螢幕通知",Toast.LENGTH_LONG).show();}}});}
   @JavascriptInterface public boolean setSpeaker(boolean on){try{AudioManager am=getSystemService(AudioManager.class);if(am==null)return false;am.setSpeakerphoneOn(on);return true;}catch(Exception e){return false;}}
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
 @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request!=SAVE_BACKUP&&request!=OPEN_BACKUP)return;try{if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri u=data.getData();if(request==SAVE_BACKUP){if(pendingBackup==null)throw new java.io.IOException("empty");try(java.io.OutputStream out=getContentResolver().openOutputStream(u,"wt")){if(out==null)throw new java.io.IOException("file");out.write(pendingBackup.getBytes(StandardCharsets.UTF_8));}Toast.makeText(this,"已儲存 VERA 備份檔",Toast.LENGTH_LONG).show();}else{java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();try(java.io.InputStream in=getContentResolver().openInputStream(u)){if(in==null)throw new java.io.IOException("file");byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1){if(out.size()+n>3000000)throw new java.io.IOException("too large");out.write(buffer,0,n);}}String raw=new String(out.toByteArray(),StandardCharsets.UTF_8);if(web!=null)web.evaluateJavascript("window.veraRestoreBackup && window.veraRestoreBackup("+org.json.JSONObject.quote(raw)+")",null);}}catch(Exception e){Toast.makeText(this,"備份操作失敗，請檢查檔案",Toast.LENGTH_LONG).show();}finally{if(request==SAVE_BACKUP)pendingBackup=null;}}
 @Override public void onRequestPermissionsResult(int r,String[] p,int[] g){
  super.onRequestPermissionsResult(r,p,g);
  if(r==42){if(web!=null)web.evaluateJavascript("window.veraRefreshReminder && window.veraRefreshReminder()",null);return;}
  if(r!=41)return;
  requestingMic=false;
  if(pending!=null){PermissionRequest req=pending;pending=null;
   if(micGranted())req.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});else req.deny();}
  if(web!=null)web.evaluateJavascript("window.veraPermissionChanged && window.veraPermissionChanged("+(micGranted()?"true":"false")+")",null);
 }
 @Override protected void onResume(){super.onResume();PushEnrollment.refresh(this);if(web!=null)web.evaluateJavascript("window.veraRefreshReminder && window.veraRefreshReminder(); window.veraReadReminder && window.veraReadReminder()",null);}
 @Override protected void onStop(){super.onStop();ReminderReceiver.inCall=false;if(web!=null&&!requestingMic)web.evaluateJavascript("window.veraBackground && window.veraBackground()",null);}
 @Override protected void onDestroy(){if(pending!=null){pending.deny();pending=null;}if(web!=null){web.removeJavascriptInterface("VeraAndroid");web.destroy();web=null;}super.onDestroy();}
}
