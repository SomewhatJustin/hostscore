import { env } from '$env/dynamic/private';
import { error } from '@sveltejs/kit';

import type { RequestHandler } from './$types';

const resolveBackendBase = (): string => {
  const configured = env.BACKEND_API_BASE?.trim();
  if (configured) {
    return configured.replace(/\/+$/, '');
  }
  return 'http://127.0.0.1:8000';
};

export const POST: RequestHandler = async ({ request, fetch }) => {
  const backendBase = resolveBackendBase();
  const target = `${backendBase}/assess`;

  let body: string;
  try {
    body = await request.text();
  } catch (cause) {
    throw error(400, 'Unable to read request payload.');
  }

  let response: Response;
  try {
    response = await fetch(target, {
      method: 'POST',
      headers: {
        'content-type': request.headers.get('content-type') ?? 'application/json'
      },
      body
    });
  } catch (cause) {
    throw error(502, 'Failed to reach backend assessor service.');
  }

  const responseBody = await response.text();
  const outgoingHeaders = new Headers();

  const contentType = response.headers.get('content-type');
  if (contentType) {
    outgoingHeaders.set('content-type', contentType);
  }

  return new Response(responseBody, {
    status: response.status,
    statusText: response.statusText,
    headers: outgoingHeaders
  });
};
