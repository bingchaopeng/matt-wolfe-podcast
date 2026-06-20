/* globals (non-module) */
function jsonToNetscapeMapper(cookies) {
  return cookies.map(
    ({ domain, expirationDate, path, secure, name, value }) => {
      const includeSubDomain = !!domain?.startsWith('.');
      const expiry = expirationDate?.toFixed() ?? '0';
      const arr = [domain, includeSubDomain, path, secure, expiry, name, value];
      return arr.map((v) =>
        typeof v === 'boolean' ? v.toString().toUpperCase() : v,
      );
    },
  );
}

const formatMap = {
  netscape: {
    ext: '.txt',
    mimeType: 'text/plain',
    serializer: (cookies) => {
      const netscapeTable = jsonToNetscapeMapper(cookies);
      const text = [
        '# Netscape HTTP Cookie File',
        '# https://curl.haxx.se/rfc/cookie_spec.html',
        '# This is a generated file! Do not edit.',
        '',
        ...netscapeTable.map((row) => row.join('\t')),
        '',
      ].join('\n');
      return text;
    },
  },
  json: {
    ext: '.json',
    mimeType: 'application/json',
    serializer: JSON.stringify,
  },
  header: {
    ext: '.txt',
    mimeType: 'text/plain',
    serializer: (cookies) => {
      return cookies.map(({ name, value }) => `${name}=${value};`).join(' ');
    },
  },
};
