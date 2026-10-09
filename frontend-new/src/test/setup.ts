import '@testing-library/jest-dom/vitest';
import axios, { AxiosError } from 'axios';
import { afterEach, beforeAll, vi } from 'vitest';
import i18n from '../i18n';

if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn()
    })
  });
}

if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    }
  };
}

if (typeof globalThis.localStorage === 'undefined') {
  Object.defineProperty(globalThis, 'localStorage', {
    writable: true,
    configurable: true,
    value: createMemoryStorage()
  });
}

const NO_NETWORK_MESSAGE =
  '[test] real network requests are disabled: mock the target service in your test, ' +
  'or override this stub via vi.stubGlobal';


const liveTimers = new Set<ReturnType<typeof setTimeout>>();
const rawSetTimeout = globalThis.setTimeout;
const rawSetInterval = globalThis.setInterval;
const rawClearTimeout = globalThis.clearTimeout;
const rawClearInterval = globalThis.clearInterval;

globalThis.setTimeout = function (...args: Parameters<typeof rawSetTimeout>) {
  const id = rawSetTimeout(...(args as unknown as Parameters<typeof setTimeout>));
  liveTimers.add(id);
  return id;
} as typeof setTimeout;

globalThis.setInterval = function (...args: Parameters<typeof rawSetInterval>) {
  const id = rawSetInterval(...(args as unknown as Parameters<typeof setInterval>));
  liveTimers.add(id);
  return id;
} as typeof setInterval;

globalThis.clearTimeout = function (...args: Parameters<typeof rawClearTimeout>) {
  const [id] = args;
  if (id !== undefined) liveTimers.delete(id as ReturnType<typeof setTimeout>);
  return rawClearTimeout(...args);
} as typeof clearTimeout;

globalThis.clearInterval = function (...args: Parameters<typeof rawClearInterval>) {
  const [id] = args;
  if (id !== undefined) liveTimers.delete(id as ReturnType<typeof setTimeout>);
  return rawClearInterval(...args);
} as typeof clearInterval;

const pendingRejects = new Set<ReturnType<typeof setTimeout>>();

const rejectOnNextTick = (makeError: () => unknown): Promise<never> =>
  new Promise((_resolve, reject) => {
    const timer = setTimeout(() => {
      pendingRejects.delete(timer);
      reject(makeError());
    }, 0);
    pendingRejects.add(timer);
  });

axios.defaults.adapter = (config) =>
  rejectOnNextTick(() => new AxiosError(NO_NETWORK_MESSAGE, AxiosError.ERR_NETWORK, config));

vi.stubGlobal('fetch', () => rejectOnNextTick(() => new Error(NO_NETWORK_MESSAGE)));

afterEach(() => {
  pendingRejects.forEach(clearTimeout);
  pendingRejects.clear();
  for (const id of liveTimers) {
    rawClearTimeout(id);
    rawClearInterval(id);
  }
  liveTimers.clear();
});

beforeAll(async () => {
  await i18n.changeLanguage('zh-CN');
});
