
  const links = document.querySelectorAll("header nav a");
  const current = window.location.pathname;
  links.forEach(link => {
  if (link.getAttribute("href") === current) {
    ink.classList.add("active");
}
});
