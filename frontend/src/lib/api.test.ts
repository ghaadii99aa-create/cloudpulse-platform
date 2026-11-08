import { api, ApiError, getToken, login, setExpiredHandler, setToken } from './api';

const respond = (status: number, body: unknown) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
  setExpiredHandler(null);
});

describe('api client', () => {
  it('sends the bearer token', async () => {
    const fetchMock = respond(200, { ok: true });
    vi.stubGlobal('fetch', fetchMock);
    setToken('abc');
    await api('/alerts');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/alerts');
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer abc');
  });

  it('turns the error envelope into an ApiError', async () => {
    vi.stubGlobal('fetch', respond(404, { error: { code: 'not_found', message: "Unknown resource 'x'" } }));
    await expect(api('/x')).rejects.toMatchObject({ status: 404, code: 'not_found', message: "Unknown resource 'x'" });
  });

  it('keeps validation details', async () => {
    vi.stubGlobal('fetch', respond(422, { error: { code: 'validation_error', message: 'bad', details: [{ field: 'metric', message: 'no' }] } }));
    const error = (await api('/x').catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.details).toEqual([{ field: 'metric', message: 'no' }]);
  });

  it('reports an unreachable API plainly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')));
    await expect(api('/x')).rejects.toMatchObject({ status: 0, code: 'network' });
  });

  it('expires the session on 401 when a token was sent', async () => {
    const expired = vi.fn();
    setExpiredHandler(expired);
    setToken('old');
    vi.stubGlobal('fetch', respond(401, { error: { code: 'unauthorized', message: 'no' } }));
    await expect(api('/x')).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledOnce();
  });

  it('does not treat a failed login as an expired session', async () => {
    const expired = vi.fn();
    setExpiredHandler(expired);
    vi.stubGlobal('fetch', respond(401, { error: { code: 'unauthorized', message: 'bad' } }));
    await expect(login('a@b.co', 'x')).rejects.toBeInstanceOf(ApiError);
    expect(expired).not.toHaveBeenCalled();
    expect(getToken()).toBeNull();
  });
});
