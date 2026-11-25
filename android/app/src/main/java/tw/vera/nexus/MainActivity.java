package tw.vera.nexus;
import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.*;
import android.widget.Toast;

public class MainActivity extends Activity {
 private WebView web; private PermissionRequest pending;
 private static final String HOST="publish-task.onrender.com";
 private boolean allowed(Uri u){ return "https".equals(u.getScheme()) && HOST.equals(u.getHost()) && (u.getPort()==-1 || u.getPort()==443); }
 @Override public void onCreate(Bundle b){
  super.onCreate(b);
  getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
  web=new WebView(this); setContentView(web);
  WebSettings s=web.getSettings(); s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true);
  s.setAllowFileAccess(false); s.setAllowContentAccess(false); s.setMediaPlaybackRequiresUserGesture(false); s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
  web.setWebViewClient(new WebViewClient(){
   @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r){return !allowed(r.getUrl());}
   @Override public void onReceivedError(WebView v,WebResourceRequest r,WebResourceError e){if(r.isForMainFrame()) Toast.makeText(MainActivity.this,"無法連線 VERA，請確認網路後重新開啟",Toast.LENGTH_LONG).show();}
  });
  web.setWebChromeClient(new WebChromeClient(){
   @Override public void onPermissionRequest(PermissionRequest r){runOnUiThread(()->{
    if(!allowed(r.getOrigin()) || !java.util.Arrays.asList(r.getResources()).contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)){r.deny();return;}
    if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED) r.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
    else {if(pending!=null) pending.deny();pending=r;requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},41);}
   });}
   @Override public void onPermissionRequestCanceled(PermissionRequest r){if(pending==r)pending=null;}
  });
  web.addJavascriptInterface(new Object(){@JavascriptInterface public void share(String t){if(t==null||t.length()>100000)return;runOnUiThread(()->{Intent i=new Intent(Intent.ACTION_SEND);i.setType("text/plain");i.putExtra(Intent.EXTRA_TEXT,t);startActivity(Intent.createChooser(i,"分享 VERA 摘要"));});}},"VeraAndroid");
  web.loadUrl("https://"+HOST+"/app");
 }
 @Override public void onRequestPermissionsResult(int r,String[] p,int[] g){super.onRequestPermissionsResult(r,p,g);if(r==41&&pending!=null){if(g.length>0&&g[0]==PackageManager.PERMISSION_GRANTED)pending.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});else pending.deny();pending=null;}}
 @Override protected void onStop(){super.onStop();if(web!=null)web.evaluateJavascript("window.veraBackground && window.veraBackground()",null);}
 @Override protected void onDestroy(){if(pending!=null)pending.deny();if(web!=null){web.removeJavascriptInterface("VeraAndroid");web.destroy();}super.onDestroy();}
}
