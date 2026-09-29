export function showCardError(cardId, msg){
  const card=document.getElementById(cardId);
  if(!card) return;
  card.classList.add("ring-2","ring-error","bg-error-container/10");
  let h=card.querySelector(".card-error-helper");
  if(!h){ h=document.createElement("div"); h.className="card-error-helper flex items-center gap-1.5 px-3 py-2 rounded-xl bg-error-container/30 border border-error/20 text-error font-body-sm mt-3"; h.innerHTML='<span class="material-symbols-outlined text-[18px]">error</span><span></span>'; card.appendChild(h); }
  h.querySelector("span:last-child").textContent=msg; h.classList.remove("hidden");
}
export function clearCardError(cardId){
  const card=document.getElementById(cardId);
  if(!card) return;
  card.classList.remove("ring-2","ring-error","bg-error-container/10");
  const h=card.querySelector(".card-error-helper");
  if(h) h.remove();
}
export function setLoading(btn, on){
  if(!btn) return;
  btn.disabled=on; btn.setAttribute("aria-busy", on?"true":"false");
  if(on){ btn.dataset.orig=btn.innerHTML; btn.innerHTML='<span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span><span>Loading...</span>'; }
  else if(btn.dataset.orig){ btn.innerHTML=btn.dataset.orig; }
}
export const validators={
  required: v=>!!String(v||"").trim()||"Required",
  email: v=>/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)||"Invalid email",
  url: v=>{ try{ new URL(v); return true;}catch{ return "Invalid URL"; } }
};
