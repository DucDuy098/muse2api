"""Qt account switching, per-account chat/sequence state and library/log filters."""
import os,sys,tempfile,time,json,base64
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from qt_studio import StudioWindow

ACCOUNTS=[{'id':'accA','label':'Tài khoản A','enabled':True,'ok':True}, {'id':'accB','label':'Tài khoản B','enabled':True,'ok':True}]
class API:
 base='http://fixture';key='fixture'
 def __init__(self):self.calls=[]
 def call(self,path,body=None,**kw):
  self.calls.append((path,body))
  if path=='/v1/studio/chat':return {'account_id':body['account_id'],'message':{'role':'assistant','content':'Phản hồi cho '+str(body['account_id'])}}
  if path=='/v1/batches':return {'id':'batch_'+body['account_id']} if body else []
  if path=='/admin/accounts':return {'accounts':ACCOUNTS}
  if path=='/admin/media':return {'media':[{'name':a['id']+'.png','kind':'image','bytes':200,'account_id':a['id']} for a in ACCOUNTS]}
  if path=='/admin/tasks':return {'tasks':[{'id':a['id']+'_task','kind':'video','status':'failed','account':a['id'],'prompt':'scene','error':'fixture error'} for a in ACCOUNTS]}
  return {}
app=QApplication([])
def wait(fn):
 end=time.monotonic()+5
 while time.monotonic()<end:
  app.processEvents()
  if fn():return
  time.sleep(.01)
 raise AssertionError('GUI callback timeout')
with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
 root=Path(tmp);(root/'data/media').mkdir(parents=True)
 for a in ACCOUNTS:
  image=QImage(240,135,QImage.Format_RGB32);image.fill(QColor('#2266aa'));image.save(str(root/'data/media'/(a['id']+'.png')))
 api=API();w=StudioWindow(workspace=root,api=api,auto_connect=False);w.show();errors=[];w.error=errors.append
 w.account_data={a['id']:a for a in ACCOUNTS};w.update_account_choices(ACCOUNTS)
 assert w.generation_options('media')['account_id'] is None
 w.media_generation_mode.set('coherent');w.media_account.set('accA');first=w.generation_options('media')
 w.media_account.set('accB');second=w.generation_options('media');assert first['sequence_id']!=second['sequence_id']
 w.media_account.set('accA');assert w.generation_options('media')['sequence_id']==first['sequence_id']
 for aid in ('accA','accB'):
  w.batch_account.set(aid);w.batch_prompts.widget.setPlainText('\n'.join('Scene '+str(i) for i in range(100)))
  w.create_batch();wait(lambda:any(p=='/v1/batches' and b and b.get('account_id')==aid for p,b in api.calls))
  app.processEvents()
 for aid in ('accA','accB'):
  w.chat_account.set(aid);w.chat_input.widget.setPlainText('Xin chào '+aid);w.send_chat();wait(lambda:not w.chat_busy)
  assert len(w.messages)==2 and w.messages[-1]['content'].endswith(aid)
 w.chat_account.set('accA');assert len(w.messages)==2 and w.messages[-1]['content'].endswith('accA')
 w.library_account.set('accA');w.log_account.set('accB');w.refresh_library()
 wait(lambda:w.library.get_children()==['accA.png'] and w.log_tasks.get_children()==['accB_task'])
 doc={'name':'kich-ban.md','data':'data:text/markdown;base64,'+base64.b64encode(b'# script').decode(),'role':'document'}
 w.references.items=[doc];w.references.render();assert w.references.payload()['reference_files']==[{'name':doc['name'],'data':doc['data']}]
 w.tabs.setCurrentWidget(w.batch_tab);app.processEvents();w.grab().save(str(ROOT/'muse2api_accounts_1.6.8.png'))
 assert not errors,errors
 w.closing=True;w.active_batches={};w.chat_busy=False;w.close();app.processEvents()
print('PASS Qt account selectors; 2 x 100 prompt submissions; per-account chat/sequence persistence; library/log filters; named document references')
