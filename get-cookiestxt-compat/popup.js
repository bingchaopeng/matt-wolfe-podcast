/* popup.js (non-module version) */
const getUrlPromise = chrome.tabs
  .query({ active: true, currentWindow: true })
  .then(([{ url }]) => new URL(url));

const getCookieText = async (details) => {
  const cookies = await getAllCookies(details);
  const format = formatMap[document.querySelector('#format').value];
  if (!format) throw new Error('Invalid format');
  const text = format.serializer(cookies);
  return { text, format };
};

const saveToFilePopup = async (text, name, { ext, mimeType }, saveAs = false) => {
  const format = { ext, mimeType };
  await saveToFile(text, name, format, saveAs);
};

const setClipboard = async (text) => {
  await navigator.clipboard.writeText(text);
  document.getElementById('copy').classList.add('copied');
  setTimeout(() => {
    document.getElementById('copy').classList.remove('copied');
  }, 2000);
};

/* Set URL in header */
getUrlPromise.then((url) => {
  const location = document.querySelector('#location');
  location.textContent = location.href = url.href;
});

/* Set cookies data to table */
getUrlPromise
  .then((url) =>
    getAllCookies({
      url: url.href,
      partitionKey: { topLevelSite: url.origin },
    }),
  )
  .then((cookies) => {
    const netscape = jsonToNetscapeMapper(cookies);
    const tableRows = netscape.map((row) => {
      const tr = document.createElement('tr');
      tr.replaceChildren(
        ...row.map((v) => {
          const td = document.createElement('td');
          td.textContent = v;
          return td;
        }),
      );
      return tr;
    });
    document.querySelector('table tbody').replaceChildren(...tableRows);
  });

/* Event listeners */
document.querySelector('#export').addEventListener('click', async () => {
  const url = await getUrlPromise;
  const details = { url: url.href, partitionKey: { topLevelSite: url.origin } };
  const { text, format } = await getCookieText(details);
  saveToFilePopup(text, `${url.hostname}_cookies`, format);
});

document.querySelector('#exportAs').addEventListener('click', async () => {
  const url = await getUrlPromise;
  const details = { url: url.href, partitionKey: { topLevelSite: url.origin } };
  const { text, format } = await getCookieText(details);
  saveToFilePopup(text, `${url.hostname}_cookies`, format, true);
});

document.querySelector('#copy').addEventListener('click', async () => {
  const url = await getUrlPromise;
  const details = { url: url.href, partitionKey: { topLevelSite: url.origin } };
  const { text } = await getCookieText(details);
  setClipboard(text);
});

document.querySelector('#exportAll').addEventListener('click', async () => {
  const { text, format } = await getCookieText({ partitionKey: {} });
  saveToFilePopup(text, 'cookies', format);
});

/* Set last used format */
const formatSelect = document.querySelector('#format');
const selectedFormat = localStorage.getItem('selectedFormat');
if (selectedFormat) formatSelect.value = selectedFormat;
formatSelect.addEventListener('change', () => {
  localStorage.setItem('selectedFormat', formatSelect.value);
});
