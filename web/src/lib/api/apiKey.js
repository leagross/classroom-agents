const API_KEY_STORAGE = "classroom_anthropic_api_key";

export function getStoredApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

export function setStoredApiKey(key) {
  localStorage.setItem(API_KEY_STORAGE, key);
}

export function clearStoredApiKey() {
  localStorage.removeItem(API_KEY_STORAGE);
}
