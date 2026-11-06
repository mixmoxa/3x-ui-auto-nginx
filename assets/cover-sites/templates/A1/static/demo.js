'use strict';
(()=>{
  const list=document.querySelector('#task-list');
  const form=document.querySelector('#task-form');
  if(!list||!form)return;
  const field=document.querySelector('#task-input');
  const counter=document.querySelector('#task-counter');
  const notice=document.querySelector('#storage-notice');
  const reset=document.querySelector('#reset-tasks');
  const storageKey='local-project-board-v1';
  const defaults=[{text:'Write a clear project brief',done:true},{text:'Collect useful references',done:true},{text:'Review the first working version',done:false},{text:'Record the final decision',done:false}];
  let tasks=defaults.map(v=>({...v}));
  let hasStorage=true;
  try{
    const raw=localStorage.getItem(storageKey);
    if(raw!==null){
      const candidate=JSON.parse(raw);
      if(Array.isArray(candidate)&&candidate.length<=100&&candidate.every(x=>x&&typeof x.text==='string'&&x.text.length<=88&&typeof x.done==='boolean')) tasks=candidate;
    }
  }catch(_){hasStorage=false;}
  notice.textContent=hasStorage?'Saved in this browser only':'Browser storage unavailable. Changes last until you leave.';
  function persist(){
    if(!hasStorage)return;
    try{localStorage.setItem(storageKey,JSON.stringify(tasks));}
    catch(_){hasStorage=false;notice.textContent='Browser storage unavailable. Changes last until you leave.';}
  }
  function render(){
    list.replaceChildren();
    const completed=tasks.filter(t=>t.done).length;
    counter.textContent=`${completed} of ${tasks.length} done`;
    if(!tasks.length){const li=document.createElement('li');li.className='loading';li.textContent='Your board is clear. Add the first step above.';list.append(li);return;}
    tasks.forEach((task,index)=>{
      const li=document.createElement('li');if(task.done)li.className='done';
      const label=document.createElement('label');
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=task.done;
      checkbox.setAttribute('aria-label',`Mark ${task.text} complete`);
      checkbox.addEventListener('change',()=>{tasks[index].done=checkbox.checked;persist();render();});
      const span=document.createElement('span');span.textContent=task.text;
      label.append(checkbox,span);
      const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.setAttribute('aria-label',`Remove ${task.text}`);
      remove.addEventListener('click',()=>{tasks.splice(index,1);persist();render();});
      li.append(label,remove);list.append(li);
    });
  }
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const value=field.value.trim();if(!value||value.length>88)return;
    if(tasks.length>=100){notice.textContent='For clarity, this example is limited to 100 tasks.';return;}
    tasks.push({text:value,done:false});field.value='';persist();render();field.focus();
  });
  reset.addEventListener('click',()=>{tasks=defaults.map(v=>({...v}));persist();render();});
  render();
})();
