import assert from 'node:assert/strict';
import {test} from 'node:test';
import {normalise,encryptBackup,readBackup} from './vera_backup.mjs';

const legacy={format:'vera-backup-1',
  tasks:[{id:'keep-task-7',title:'合成測試待辦',priority:'high',due:'2027-01-04T09:00:00',done:false}],
  histories:[{id:'123',at:'2026-11-27',rows:[{role:'你',text:'合成決策'}],summary:'同意測試'}],
  notes:'回復內容',assistantProfile:{name:'驗收',autoReconnect:true,memory:'模擬專案'},
  usage:{seconds:13,estimatedUSD:.02},callLimit:20,accessToken:'must-never-be-exported'};
const passphrase='synthetic-backup-test-passphrase';

test('legacy import preserves stable reminder IDs and drops credentials', async () => {
  const actual=await readBackup(JSON.stringify(legacy));
  assert.equal(actual.tasks[0].id,'keep-task-7');
  assert.equal(actual.histories[0].id,'123');
  assert.equal(actual.notes,'回復內容');
  assert.equal(actual.assistantProfile.autoReconnect,true);
  assert.equal(actual.usage.estimatedUSD,.02);
  assert.equal(Object.hasOwn(actual,'accessToken'),false);
  const copy=normalise({...legacy,tasks:[legacy.tasks[0],legacy.tasks[0]]});
  assert.notEqual(copy.tasks[0].id,copy.tasks[1].id);
});

test('portable encrypted archive verifies wrong passwords and data modification',async()=>{
  const encoded=await encryptBackup(legacy,passphrase);
  assert.notEqual(encoded,await encryptBackup(legacy,passphrase));
  assert.equal(encoded.includes('回復內容'),false);
  assert.equal(encoded.includes('must-never-be-exported'),false);
  assert.deepEqual(await readBackup(encoded,passphrase),normalise(legacy));
  await assert.rejects(readBackup(encoded,'wrong-backup-password'),/無法還原/);
  const damaged=JSON.parse(encoded);
  damaged.ciphertext=(damaged.ciphertext[0]==='A'?'B':'A')+damaged.ciphertext.slice(1);
  await assert.rejects(readBackup(JSON.stringify(damaged),passphrase),/無法還原/);
});
