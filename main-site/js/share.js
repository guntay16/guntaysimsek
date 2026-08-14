document.querySelectorAll('.copy-link').forEach(function(btn){
  btn.addEventListener('click', function(){
    navigator.clipboard.writeText(btn.dataset.url).then(function(){
      var original = btn.textContent;
      btn.textContent = 'Kopyalandı';
      btn.classList.add('copied');
      setTimeout(function(){
        btn.textContent = original;
        btn.classList.remove('copied');
      }, 1500);
    });
  });
});
