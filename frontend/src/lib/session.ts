import { writable } from 'svelte/store';
import type { SessionInfo } from './types';

const defaultSession: SessionInfo = { authenticated: false };

export const sessionStore = writable<SessionInfo>(defaultSession);

export const setSession = (session: SessionInfo) => {
  sessionStore.set(session);
};

export const resetSession = () => {
  sessionStore.set(defaultSession);
};
