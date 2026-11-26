// Serialize the explicitly authorized Life OS model calls in this page.
(()=>{let tail=Promise.resolve();window.lifeOSAI=task=>{const next=tail.then(task,task);tail=next.catch(()=>{});return next;};})();
