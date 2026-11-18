try { var s = localStorage.getItem("medagentbench-reader-theme"); if (s === "light" || s === "dark") document.documentElement.setAttribute("data-theme", s); } catch (e) {}
