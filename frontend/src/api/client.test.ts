import { describe, it, expect, vi, afterEach } from 'vitest';

import { api, ApiError } from './client';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('api client error parsing', () => {
  it('throws ApiError with parsed JSON detail', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      text: async () =>
        JSON.stringify({
          detail: 'LLM response error: Check TEXTRACTOR_LLM_MODEL is valid for the configured provider.',
        }),
    } as Response);

    await expect(api.preannotateDocument('doc-1')).rejects.toBeInstanceOf(ApiError);

    try {
      await api.preannotateDocument('doc-1');
      expect.fail('Expected ApiError to be thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(502);
      expect(apiErr.statusText).toBe('Bad Gateway');
      expect(apiErr.detail).toContain('TEXTRACTOR_LLM_MODEL');
      expect(apiErr.message).toContain('502 Bad Gateway');
    }

    expect(fetchMock).toHaveBeenCalled();
  });

  it('falls back to raw body when error response is plain text', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => 'something broke',
    } as Response);

    try {
      await api.preannotateDocument('doc-2');
      expect.fail('Expected ApiError to be thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.detail).toBe('something broke');
      expect(apiErr.body).toBe('something broke');
    }
  });
});
