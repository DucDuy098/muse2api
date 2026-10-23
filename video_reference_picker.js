/* Shared local image picker for batch and single-video creation. */
class VideoReferencePicker {
  constructor(id) {
    this.root = document.getElementById(id);
    this.items = [];
    this.inputExtensions = '.png,.jpg,.jpeg,.webp,.md,.txt,.csv,.xlsx,.xls,.pdf,.docx';
    this.loading = false;
    this.input = this.root.querySelector('input[type=file]');
    this.input.accept=this.inputExtensions;
    this.preview = this.root.querySelector('.reference-preview');
    this.status = this.root.querySelector('.reference-status');
    this.input.addEventListener('change', () => this.add(Array.from(this.input.files)));
    this.root.querySelector('.reference-clear').onclick = () => { this.items = []; this.render(); };
  }
  async add(files) {
    this.loading = true;
    this.input.disabled = true;
    try {
      if (this.items.length + files.length > 16) throw Error('Tối đa 8 ảnh và 8 tài liệu');
      let total = this.items.reduce((n, x) => n + x.size, 0);
      const added = [];
      for (const file of files) {
        const documentFile=/\.(md|txt|csv|xlsx|xls|pdf|docx)$/i.test(file.name);
        if (!documentFile && !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw Error('Hỗ trợ ảnh và MD/TXT/CSV/Excel/PDF/DOCX');
        if (!file.size || file.size > 5 * 1024 * 1024) throw Error('Mỗi ảnh tối đa 5 MB');
        total += file.size;
        if (total > 20 * 1024 * 1024) throw Error('Tổng ảnh mẫu tối đa 20 MB');
        const data = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(Error('Không đọc được ảnh ' + file.name));
          reader.readAsDataURL(file);
        });
        added.push({name: file.name, size: file.size, data, role: documentFile?'document':'reference'});
      }
      this.items.push(...added);
      this.render();
    } catch (e) { this.status.textContent = e.message; }
    finally { this.loading = false; this.input.disabled = false; this.input.value = ''; }
  }
  payload() {
    if (this.loading) throw Error('Đang đọc ảnh mẫu, vui lòng chờ');
    return {reference_images: this.items.filter(x=>x.role!=='document').map(x => x.data), reference_roles: this.items.filter(x=>x.role!=='document').map(x => x.role),reference_files:this.items.filter(x=>x.role==='document').map(x=>({name:x.name,data:x.data}))};
  }
  render() {
    this.preview.replaceChildren();
    this.items.forEach((item, index) => {
      const card = document.createElement('div');
      card.style.cssText = 'display:inline-flex;flex-direction:column;gap:6px;width:180px;margin:8px;vertical-align:top';
      const image = document.createElement('img');
      if(item.role!=='document') image.src = item.data; image.alt = item.name;
      image.style.cssText = 'width:180px;height:120px;object-fit:contain;background:#0d1422;border-radius:8px';
      const label = document.createElement('span');
      label.textContent = (index + 1) + '. ' + item.name;
      label.style.overflowWrap = 'anywhere';
      const role = document.createElement('select');
      role.setAttribute('aria-label', 'Vai trò ảnh ' + (index + 1));
      for (const [value, text] of [['reference','Tham khảo chung'],['character','Nhân vật'],['scene','Bối cảnh'],['background','Nền'],['first_frame','Khung hình đầu']]) {
        const option = document.createElement('option'); option.value = value; option.textContent = text; role.append(option);
      }
      if(item.role==='document'){const option=document.createElement('option');option.value='document';option.textContent='Tài liệu';role.append(option);role.disabled=true;}
      role.value = item.role; role.onchange = () => { item.role = role.value; };
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Bỏ ảnh ' + (index + 1);
      remove.onclick = () => { this.items.splice(index, 1); this.render(); };
      card.append(image, label, role, remove); this.preview.append(card);
    });
    this.status.textContent = this.items.length ? 'Đã chọn ' + this.items.length + ' tệp. Ghi rõ cách dùng từng tệp trong prompt.' : 'Chưa chọn ảnh: tạo từ mô tả.';
  }
}

async function museAccountChoices(api,ids){
 const response=await api('/admin/accounts');window.museAccounts=response.accounts||[];
 for(const id of ids){const select=document.getElementById(id);if(!select)continue;
  const old=select.value;select.replaceChildren();const filter=select.dataset.filter==='true';
  const add=(name,value)=>{const o=document.createElement('option');o.textContent=name;o.value=value;select.append(o)};
  add(filter?'Tất cả tài khoản':'Tự động chọn','');if(filter)add('Chưa phân loại','unassigned');
  for(const a of window.museAccounts)if(filter||a.enabled)add(a.label+' · '+a.id,a.id);
  if(old&&![...select.options].some(o=>o.value===old))add(old+' (không khả dụng)',old);
  select.value=old;
 }
 document.dispatchEvent(new Event('muse-accounts-ready'));
}
async function museChooseAccount(api){
 if(!window.museAccounts)await museAccountChoices(api,[]);
 return await new Promise(resolve=>{
 const d=document.createElement('dialog');d.style.cssText='background:#121a2b;color:#edf3ff;padding:24px;border:1px solid #4f8cff';
 const label=document.createElement('p');label.textContent='Tạo độc lập bằng tài khoản khác (hội thoại mới):';d.append(label);
 const select=document.createElement('select');for(const a of window.museAccounts||[])if(a.enabled){const o=document.createElement('option');o.value=a.id;o.textContent=a.label;select.append(o)}d.append(select);
 for(const [text,accept]of[['Tạo riêng',true],['Hủy',false]]){const b=document.createElement('button');b.textContent=text;b.onclick=()=>{resolve(accept?select.value:null);d.close();d.remove()};d.append(b)}
 d.oncancel=()=>{resolve(null);d.remove()};document.body.append(d);d.showModal();
 });
}
