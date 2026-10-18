const names={quick:'Quick checks',scenarios:'Scenario checks',games:'Full game checks'};
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function validationMarkup(report){
  return `<div class="validation-stages" aria-label="Upload validation">${Object.entries(names).map(([key,name])=>{
    const stage=report.stages[key],state=stage.status;
    const symbol={passed:'✓',failed:'✕',pending:'○',skipped:'–',running:'↻'}[state]||'○';
    const details=stage.details;
    return `<section class="validation-stage ${escape(state)}" data-validation-stage="${key}">
      <div class="validation-stage-title"><span class="validation-icon" aria-hidden="true">${symbol}</span><strong>${name}</strong><span class="muted">${escape(state==='passed'?'Passed':state==='running'?'Running':state==='failed'?'Failed':state==='skipped'?'Not run':'Waiting')}</span></div>
      <p class="muted">${escape(stage.message)}</p>
      ${stage.total?`<progress max="${stage.total}" value="${stage.completed||0}" aria-label="${name} progress"></progress>`:''}
      ${stage.games?.length?`<ul>${stage.games.map(g=>`<li>Seed ${g.seed} · ${escape(g.seat)} · ${g.turns} turns · ${escape(g.status==='completed'?'Finished':'Simulation limit reached')}</li>`).join('')}</ul>`:''}
      ${details?`<details open><summary>Error details</summary><p class="form-error">${escape(details.error)}</p>${details.scenario?`<p>Scenario: ${escape(details.scenario)}</p>`:''}${details.callback?`<p>Callback: ${escape(details.callback)} · phase ${escape(details.phase)} · turn ${escape(details.turn_number)}</p>`:''}${details.returned_action!==undefined?`<h4>Returned action</h4><pre>${escape(JSON.stringify(details.returned_action,null,2))}</pre>`:''}${details.available_types?`<p>Available actions: ${escape(details.available_types.join(', '))}</p>`:''}${details.hint?`<p>${escape(details.hint)}</p>`:''}${details.traceback?`<h4>Stack trace</h4><pre>${escape(details.traceback)}</pre>`:''}${details.available_actions?`<details><summary>Legal options for this decision</summary><pre>${escape(JSON.stringify(details.available_actions,null,2))}</pre></details>`:''}${details.player_view?`<details><summary>Your player's view</summary><pre>${escape(JSON.stringify(details.player_view,null,2))}</pre></details>`:''}</details>`:''}
    </section>`;
  }).join('')}</div>`;
}

export async function validateUpload(form,data,{api,modal,onSaved,onTest,testAfter=false}){
  form.dataset.validationBusy='true';
  form.querySelector('.upload-validation')?.remove();
  const panel=document.createElement('div');panel.className='upload-validation';form.append(panel);
  const controls=[...form.querySelectorAll('input,textarea,button')];
  const previous=controls.map(control=>control.disabled);controls.forEach(control=>control.disabled=true);
  const draw=report=>{panel.innerHTML=validationMarkup(report);};
  draw({stages:Object.fromEntries(Object.keys(names).map(key=>[key,{status:'pending',message:'Waiting'}]))});
  panel.scrollIntoView({block:'start'});
  let succeeded=false;
  try{
    let report=await api('/bots/upload?wait=false',data);
    draw(report);
    while(['queued','running'].includes(report.status)){
      await new Promise(resolve=>setTimeout(resolve,500));
      report=await api(`/bots/validations/${encodeURIComponent(report.validation_id)}`);draw(report);
    }
    if(report.status!=='passed')return;
    succeeded=true;
    form.dataset.validationPassed='true';
    const message=document.createElement('p');message.className='validation-success';message.textContent='Player version saved. Validation games are excluded from your match history.';panel.append(message);
    const done=document.createElement('button');done.type='button';done.className='primary';done.textContent=testAfter?'Continue to test room':'Done';panel.append(done);
    done.onclick=async()=>{modal.close();await onSaved();if(testAfter)await onTest(report.bot_id);};
    done.scrollIntoView({block:'nearest'});
  }finally{
    form.dataset.validationBusy='false';
    if(!succeeded)controls.forEach((control,index)=>control.disabled=previous[index]);
  }
}
