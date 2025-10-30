import type { LayoutLoad } from './$types';
import { fetchSession } from '$lib/api';

export const load: LayoutLoad = async ({ fetch }) => {
  const session = await fetchSession(fetch);
  return { session };
};
