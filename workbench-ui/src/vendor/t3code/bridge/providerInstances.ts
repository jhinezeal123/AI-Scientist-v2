export function normalizeProviderAccentColor(value:string|null|undefined){return value&&/^#[0-9a-f]{6}$/i.test(value)?value.toLowerCase():undefined;}
