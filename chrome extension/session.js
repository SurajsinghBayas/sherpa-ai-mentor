// Runs on sherpa-ai.tech tabs. Google and GitHub sign-in can't run inside the side panel's frame,
// so people sign in on the site; this hands that session to the panel (and sign-out too).
(() => {
  let last; // undefined until the first look, so a tab that was never signed in doesn't sign the panel out
  const look = () => {
    let token;
    try {
      token = localStorage.getItem("sherpa.jwt");
    } catch {
      return;
    }
    if (token === last) return;
    if (token || last !== undefined) chrome.storage.local.set({ token: token || null }).catch(() => {});
    last = token;
  };
  look();
  setInterval(look, 1500);
})();
