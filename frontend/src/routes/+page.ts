import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  const prefillUrl = url.searchParams.get('url') ?? '';

  if (prefillUrl) {
    throw redirect(302, '/');
  }

  return {
    prefillUrl: ''
  };
};
