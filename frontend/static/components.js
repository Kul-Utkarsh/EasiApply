export function Card({children, elevated=false, className=""}){
  return `<div class="card ${elevated?"card-elevated":""} ${className}">${children}</div>`;
}
export function Button({variant="primary", size="md", children, ...props}){
  const variants={primary:"btn-primary", secondary:"btn-secondary", ghost:"btn-ghost", danger:"btn-danger"};
  const sizes={sm:"px-3 py-1.5 text-sm", md:"px-4 py-2", lg:"px-6 py-3"};
  return `<button class="btn ${variants[variant]||variants.primary} ${sizes[size]||sizes.md} ${props.className||""}" ${Object.entries(props).map(([k,v])=>`${k}="${v}"`).join(" ")}>${children}</button>`;
}
export function Input({label, id, type="text", placeholder="", value="", error, ...props}){
  return `<label class="stack gap-xs" for="${id}">${label}<input id="${id}" type="${type}" class="input ${error?"input-error":""}" placeholder="${placeholder}" value="${value}" ${Object.entries(props).map(([k,v])=>`${k}="${v}"`).join(" ")} />${error?`<span class="error-text">${error}</span>`:""}</label>`;
}
