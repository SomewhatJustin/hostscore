import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  const prefillUrl = url.searchParams.get('url') ?? '';

  return {
    prefillUrl
  };
};
