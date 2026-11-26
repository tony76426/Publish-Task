package tw.vera.nexus;
import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.os.*;
import android.view.*;
import android.widget.*;

public final class IncomingActivity extends Activity {
 private long id;private final Handler timer=new Handler(Looper.getMainLooper());
 private TextView label;
 private final Runnable tick=new Runnable(){public void run(){if(!ReminderReceiver.active(IncomingActivity.this,id)){ReminderReceiver.finishCall(IncomingActivity.this,id,"missed");finish();return;}label.setText("VERA 主動聯繫 · "+Math.max(1,(id+ReminderReceiver.RING_MS-System.currentTimeMillis()+999)/1000)+" 秒");timer.postDelayed(this,500);}};
 @Override public void onCreate(Bundle b){super.onCreate(b);id=getIntent().getLongExtra("id",0);if(!ReminderReceiver.active(this,id)){finish();return;}if(Build.VERSION.SDK_INT>=27){setShowWhenLocked(true);setTurnScreenOn(true);}else getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED|WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
 LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setGravity(Gravity.CENTER);root.setPadding(30,30,30,30);root.setBackgroundColor(Color.rgb(19,41,66));setContentView(root);
 TextView brand=new TextView(this);brand.setText("V E R A");brand.setTextColor(Color.WHITE);brand.setTextSize(38);brand.setGravity(Gravity.CENTER);root.addView(brand);
 ImageView image=new ImageView(this);image.setImageResource(R.drawable.vera);LinearLayout.LayoutParams ip=new LinearLayout.LayoutParams(220,220);ip.topMargin=40;ip.bottomMargin=35;root.addView(image,ip);
 label=new TextView(this);label.setTextColor(Color.WHITE);label.setTextSize(21);label.setGravity(Gravity.CENTER);root.addView(label);
 TextView info=new TextView(this);info.setText("AI 私人秘書 · 本機來電提醒");info.setTextColor(Color.rgb(191,209,228));info.setGravity(Gravity.CENTER);root.addView(info);
 LinearLayout actions=new LinearLayout(this);actions.setGravity(Gravity.CENTER);LinearLayout.LayoutParams ap=new LinearLayout.LayoutParams(-1,-2);ap.topMargin=45;root.addView(actions,ap);
 Button no=new Button(this);no.setText("拒絕");Button yes=new Button(this);yes.setText("接聽");actions.addView(no,new LinearLayout.LayoutParams(0,-2,1));actions.addView(yes,new LinearLayout.LayoutParams(0,-2,1));no.setOnClickListener(v->{ReminderReceiver.finishCall(this,id,"declined");finish();});yes.setOnClickListener(v->accept());timer.post(tick);
 }
 private void accept(){if(!ReminderReceiver.active(this,id)){finish();return;}KeyguardManager k=getSystemService(KeyguardManager.class);if(Build.VERSION.SDK_INT>=26&&k!=null&&k.isKeyguardLocked()){k.requestDismissKeyguard(this,new KeyguardManager.KeyguardDismissCallback(){public void onDismissSucceeded(){open();}});}else open();}
 private void open(){if(!ReminderReceiver.active(this,id)){finish();return;}String kind=ReminderReceiver.prefs(this).getString("activeKind","daily");String nonce=java.util.UUID.randomUUID().toString();ReminderReceiver.prefs(this).edit().putString("acceptNonce",nonce).commit();ReminderReceiver.finishCall(this,id,"opened");startActivity(new Intent(this,MainActivity.class).setAction(ReminderReceiver.OPEN).putExtra("reminder_kind",kind).putExtra("accept_nonce",nonce).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP));finish();}
 @Override public void onBackPressed(){ReminderReceiver.finishCall(this,id,"declined");finish();}
 @Override protected void onDestroy(){timer.removeCallbacksAndMessages(null);super.onDestroy();}
}
