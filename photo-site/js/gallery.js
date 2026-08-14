async function loadPhotos(){
  const el = document.getElementById('photos-data');
  return JSON.parse(el.textContent);
}

function init(ITEMS){
  const CATEGORY_ORDER = ["Ay ve Uçak","Havalimanları","Havacılık","Hava Gösterisi","Hayvanlar","Portre","Ağaçlar","Şehirler","Seyahat"];
  const categories = ["Tümü", ...CATEGORY_ORDER.filter(c=>ITEMS.some(i=>i.cat===c))];
  const filtersEl = document.getElementById('filters');
  const gridEl = document.getElementById('grid');
  let activeCat = "Tümü";

  function renderFilters(){
    filtersEl.innerHTML = "";
    categories.forEach(cat=>{
      const btn = document.createElement('button');
      btn.className = 'filter-btn' + (cat===activeCat ? ' active' : '');
      btn.textContent = cat;
      btn.onclick = ()=>{ activeCat = cat; renderFilters(); renderGrid(); };
      filtersEl.appendChild(btn);
    });
  }

  function buildTile(item, idx){
    const tile = document.createElement('div');
    tile.className = 'tile' + (item.wide ? ' tile-wide' : '');
    tile.innerHTML = `<img src="${item.thumb}" alt="${item.caption}" loading="lazy">
      <div class="tile-cap"><span class="tile-cat">${item.cat}</span>${item.caption}</div>`;
    tile.onclick = ()=> openLightbox(idx);
    return tile;
  }

  function columnCount(){
    const w = window.innerWidth;
    if(w < 640) return 1;
    if(w < 960) return 2;
    if(w < 1280) return 3;
    return 4;
  }

  function renderMasonry(container, group, indexOf){
    const wide = group.filter(item=>item.wide);
    const normal = group.filter(item=>!item.wide);

    wide.forEach(item=>{
      container.appendChild(buildTile(item, indexOf(item)));
    });

    if(normal.length===0) return;
    const gridDiv = document.createElement('div');
    gridDiv.className = 'grid';
    const cols = [];
    const n = Math.min(columnCount(), normal.length);
    for(let i=0;i<n;i++){
      const col = document.createElement('div');
      col.className = 'grid-col';
      cols.push(col);
      gridDiv.appendChild(col);
    }
    normal.forEach((item, i)=>{
      cols[i % n].appendChild(buildTile(item, indexOf(item)));
    });
    container.appendChild(gridDiv);
  }

  let visibleItems = [];
  function renderGrid(){
    gridEl.innerHTML = "";
    if(activeCat === "Tümü"){
      const tumuCategories = CATEGORY_ORDER.filter(cat=>cat!=='Ay ve Uçak');
      visibleItems = tumuCategories.flatMap(cat=>ITEMS.filter(i=>i.cat===cat));
      tumuCategories.forEach(cat=>{
        const group = ITEMS.filter(i=>i.cat===cat);
        if(group.length===0) return;
        const section = document.createElement('div');
        section.className = 'cat-section';
        const heading = document.createElement('h3');
        heading.className = 'cat-heading';
        heading.textContent = cat;
        section.appendChild(heading);
        renderMasonry(section, group, item=>visibleItems.indexOf(item));
        gridEl.appendChild(section);
      });
    } else {
      visibleItems = ITEMS.filter(i=>i.cat===activeCat);
      renderMasonry(gridEl, visibleItems, item=>visibleItems.indexOf(item));
    }
  }

  const lightbox = document.getElementById('lightbox');
  const lbImg = document.getElementById('lbImg');
  const lbCat = document.getElementById('lbCat');
  const lbCaption = document.getElementById('lbCaption');
  const lbShareX = document.getElementById('lbShareX');
  const lbShareWa = document.getElementById('lbShareWa');
  const lbCopyLink = document.getElementById('lbCopyLink');
  let currentIdx = 0;

  function openLightbox(idx){
    currentIdx = idx;
    showCurrent();
    lightbox.classList.add('open');
  }
  function showCurrent(){
    const item = visibleItems[currentIdx];
    lbImg.src = item.full;
    lbCat.textContent = item.cat;
    lbCaption.textContent = item.caption;

    const shareUrl = location.origin + location.pathname;
    const shareText = item.caption + ' — Güntay Şimşek Fotoğraf';
    lbShareX.href = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent(shareText) + '&url=' + encodeURIComponent(shareUrl);
    lbShareWa.href = 'https://wa.me/?text=' + encodeURIComponent(shareText + ' ' + shareUrl);
    lbCopyLink.dataset.url = shareUrl;
  }
  document.getElementById('lbClose').onclick = ()=> lightbox.classList.remove('open');
  document.getElementById('lbPrev').onclick = ()=>{ currentIdx = (currentIdx-1+visibleItems.length)%visibleItems.length; showCurrent(); };
  document.getElementById('lbNext').onclick = ()=>{ currentIdx = (currentIdx+1)%visibleItems.length; showCurrent(); };
  lightbox.addEventListener('click', (e)=>{ if(e.target===lightbox) lightbox.classList.remove('open'); });
  document.addEventListener('keydown', (e)=>{
    if(!lightbox.classList.contains('open')) return;
    if(e.key==='Escape') lightbox.classList.remove('open');
    if(e.key==='ArrowLeft') document.getElementById('lbPrev').click();
    if(e.key==='ArrowRight') document.getElementById('lbNext').click();
  });

  lbCopyLink.addEventListener('click', ()=>{
    navigator.clipboard.writeText(lbCopyLink.dataset.url).then(()=>{
      const original = lbCopyLink.textContent;
      lbCopyLink.textContent = 'Kopyalandı';
      lbCopyLink.classList.add('copied');
      setTimeout(()=>{
        lbCopyLink.textContent = original;
        lbCopyLink.classList.remove('copied');
      }, 1500);
    });
  });

  document.querySelectorAll('.series-tile, .series-hero').forEach(tile=>{
    tile.addEventListener('click', ()=>{
      const caption = tile.dataset.caption;
      activeCat = 'Ay ve Uçak';
      renderFilters();
      renderGrid();
      const idx = visibleItems.findIndex(i=>i.caption===caption);
      openLightbox(idx===-1 ? 0 : idx);
    });
  });

  renderFilters();
  renderGrid();
}

loadPhotos().then(init).catch(err=>{
  document.getElementById('grid').innerHTML = '<p class="empty-state">Fotoğraflar yüklenemedi.</p>';
  console.error(err);
});
