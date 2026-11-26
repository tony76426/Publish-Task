package tw.vera.nexus;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;
import java.util.Calendar;

public final class ReminderReceiver extends BroadcastReceiver {
 static final String CHANNEL="vera_scheduled_calls_v1";
 static final String PREFS="vera_reminders";
 static final String DAILY="tw.vera.nexus.DAILY";
 static final String TEST="tw.vera.nexus.TEST";
 static final String OPEN="tw.vera.nexus.OPEN_REMINDER";
 static final int DAILY_ID=801, TEST_ID=802;
 static SharedPreferences prefs(Context c){return c.getSharedPreferences(PREFS,Context.MODE_PRIVATE);}
 static boolean notifyAllowed(Context c){
  NotificationManager n=c.getSystemService(NotificationManager.class);
  if(n==null||!n.areNotificationsEnabled())return false;
  if(Build.VERSION.SDK_INT>=33&&c.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return false;
  NotificationChannel ch=n.getNotificationChannel(CHANNEL);
  return ch==null||ch.getImportance()!=NotificationManager.IMPORTANCE_NONE;
 }
 static boolean exactAllowed(Context c){AlarmManager a=c.getSystemService(AlarmManager.class);return a!=null&&(Build.VERSION.SDK_INT<31||a.canScheduleExactAlarms());}
 static void channel(Context c){
  NotificationManager n=c.getSystemService(NotificationManager.class);
  if(n==null)return;
  NotificationChannel ch=new NotificationChannel(CHANNEL,"VERA 主動聯繫提醒",NotificationManager.IMPORTANCE_HIGH);
  ch.setDescription("每日工作報告與測試來電提醒");ch.enableVibration(true);
  ch.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE);
  ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).build());
  n.createNotificationChannel(ch);
 }
 static PendingIntent alarmIntent(Context c,boolean test){
  Intent i=new Intent(c,ReminderReceiver.class).setAction(test?TEST:DAILY);
  return PendingIntent.getBroadcast(c,test?TEST_ID:DAILY_ID,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
 }
 static boolean schedule(Context c,boolean test,long when){
  AlarmManager a=c.getSystemService(AlarmManager.class);if(a==null)return false;
  PendingIntent p=alarmIntent(c,test);
  try{if(exactAllowed(c)){a.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,when,p);}else{a.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,when,p);}return true;}
  catch(SecurityException ex){try{a.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,when,p);return true;}catch(RuntimeException e){return false;}}
  catch(RuntimeException ex){return false;}
 }
 static long nextDaily(int hour,int minute){
  Calendar x=Calendar.getInstance();x.set(Calendar.HOUR_OF_DAY,hour);x.set(Calendar.MINUTE,minute);x.set(Calendar.SECOND,0);x.set(Calendar.MILLISECOND,0);
  if(x.getTimeInMillis()<=System.currentTimeMillis())x.add(Calendar.DAY_OF_YEAR,1);
  return x.getTimeInMillis();
 }
 static boolean configure(Context c,int hour,int minute){
  if(hour<0||hour>23||minute<0||minute>59)return false;
  channel(c);long when=nextDaily(hour,minute);
  if(!prefs(c).edit().putBoolean("enabled",true).putInt("hour",hour).putInt("minute",minute).putLong("next",when).commit())return false;
  if(schedule(c,false,when))return true;
  cancelDaily(c);return false;
 }
 static void cancelDaily(Context c){
  prefs(c).edit().putBoolean("enabled",false).remove("next").commit();
  AlarmManager a=c.getSystemService(AlarmManager.class);if(a!=null)a.cancel(alarmIntent(c,false));
  NotificationManager n=c.getSystemService(NotificationManager.class);if(n!=null)n.cancel(DAILY_ID);
 }
 static void cancelAll(Context c){
  cancelDaily(c);AlarmManager a=c.getSystemService(AlarmManager.class);if(a!=null)a.cancel(alarmIntent(c,true));
  NotificationManager n=c.getSystemService(NotificationManager.class);if(n!=null)n.cancel(TEST_ID);
 }
 @Override public void onReceive(Context c,Intent i){
  String action=i.getAction();if(action==null)return;
  if(Intent.ACTION_BOOT_COMPLETED.equals(action)||Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)||Intent.ACTION_TIME_CHANGED.equals(action)||Intent.ACTION_TIMEZONE_CHANGED.equals(action)||AlarmManager.ACTION_SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED.equals(action)){
   SharedPreferences p=prefs(c);if(p.getBoolean("enabled",false))configure(c,p.getInt("hour",9),p.getInt("minute",0));return;
  }
  boolean test=TEST.equals(action);if(!test&&!DAILY.equals(action))return;
  SharedPreferences p=prefs(c);
  if(!test){if(!p.getBoolean("enabled",false))return;configure(c,p.getInt("hour",9),p.getInt("minute",0));}
  channel(c);if(!notifyAllowed(c))return;
  int id=test?TEST_ID:DAILY_ID;
  Intent open=new Intent(c,MainActivity.class).setAction(OPEN).putExtra("reminder_kind",test?"test":"daily").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
  PendingIntent tap=PendingIntent.getActivity(c,id,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
  Notification n=new Notification.Builder(c,CHANNEL).setSmallIcon(android.R.drawable.ic_dialog_info)
   .setContentTitle("VERA 主動聯繫").setContentText(test?"測試提醒：點擊進入接聽畫面":"每日工作彙報：點擊進入接聽畫面")
   .setCategory(Notification.CATEGORY_REMINDER).setVisibility(Notification.VISIBILITY_PRIVATE).setAutoCancel(true)
   .setContentIntent(tap).addAction(new Notification.Action.Builder(null,"開啟接聽畫面",tap).build()).build();
  NotificationManager nm=c.getSystemService(NotificationManager.class);if(nm!=null)nm.notify(id,n);
 }
}
