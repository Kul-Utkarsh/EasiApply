export const State={IDLE:"idle", LOADING:"loading", SUCCESS:"success", ERROR:"error", PARTIAL:"partial", UNAUTHORIZED:"unauthorized", TIMEOUT:"timeout"};
export function showState(section, state, payload){
  const el=document.getElementById(`state-${state}`);
  if(el) window.__showState?.(state);
}
export function showPartial(section, successItems, errorItems){
  // For list views: render successes, badge errors
}
