async function loadPhotos(){
  const el = document.getElementById('photos-data');
  return JSON.parse(el.textContent);
}

function pictureHTML(item, kind, sizesAttr, className, extraAttrs){
  // kind: 'thumb' uses thumb as 1x / full as ~1.43x; 'full' uses full only (lightbox)
  const base = item.thumb.replace(/\.jpg$/, '');
  const fullBase = item.full.replace(/\.jpg$/, '');
  const w = kind === 'thumb' ? item.w : item.fw;
  const h = kind === 'thumb' ? item.h : item.fh;
  let avifSrcset, webpSrcset, jpgSrcset, jpgSrc;
  if(kind === 'thumb'){
    avifSrcset = `${base}.avif ${item.w}w, ${fullBase}.avif ${item.fw}w`;
    webpSrcset = `${base}.webp ${item.w}w, ${fullBase}.webp ${item.fw}w`;
    jpgSrcset  = `${item.thumb} ${item.w}w, ${item.full} ${item.fw}w`;
    jpgSrc = item.thumb;
  } else {
    avifSrcset = `${fullBase}.avif ${item.fw}w`;
    webpSrcset = `${fullBase}.webp ${item.fw}w`;
    jpgSrcset  = `${item.full} ${item.fw}w`;
    jpgSrc = item.full;
  }
  return `<picture>
      <source type="image/avif" srcset="${avifSrcset}"${sizesAttr}>
      <source type="image/webp" srcset="${webpSrcset}"${sizesAttr}>
      <img class="${className}" src="${jpgSrc}" srcset="${jpgSrcset}"${sizesAttr} width="${w}" height="${h}" alt="${item.caption}" ${extraAttrs||''}>
    </picture>`;
}

function init(ITEMS){
  const bySlug = {};
  ITEMS.forEach(i=>{ bySlug[i.slug] = i; });

  const CATEGORY_ORDER = ["Ay'la Yolculuk","Havalimanları","Havadan","Hava Gösterisi","Hayvanlar","Portre","Ağaçlar","Şehirler","Seyahat"];
  const CATEGORY_LABELS_EN = {
    "Tümü":"All","Ay'la Yolculuk":"Journey with the Moon","Havalimanları":"Airports","Havadan":"Aerial",
    "Hava Gösterisi":"Air Show","Hayvanlar":"Animals","Portre":"Portrait","Ağaçlar":"Trees",
    "Şehirler":"Cities","Seyahat":"Travel"
  };
  function catLabel(cat){
    return CATEGORY_LABELS_EN[cat] ? cat + ' / ' + CATEGORY_LABELS_EN[cat] : cat;
  }
  const categories = ["Tümü", ...CATEGORY_ORDER.filter(c=>ITEMS.some(i=>i.cat===c))];
  const filtersEl = document.getElementById('filters');
  const gridEl = document.getElementById('grid');
  let activeCat = "Tümü";

  function renderFilters(){
    filtersEl.innerHTML = "";
    categories.forEach(cat=>{
      const btn = document.createElement('button');
      const isActive = cat===activeCat;
      btn.className = 'filter-btn' + (isActive ? ' active' : '');
      btn.textContent = catLabel(cat);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      btn.onclick = ()=>{ activeCat = cat; renderFilters(); renderGrid(); };
      filtersEl.appendChild(btn);
    });
  }

  function buildTile(item, idx){
    const tile = document.createElement('div');
    tile.className = 'tile' + (item.wide ? ' tile-wide' : '');
    const sizes = ' sizes="(max-width:639px) 100vw, (max-width:899px) 50vw, (max-width:1199px) 33vw, 25vw"';
    tile.innerHTML = `${pictureHTML(item, 'thumb', sizes, '', 'loading="lazy"')}
      <div class="tile-cap"><span class="tile-cat">${catLabel(item.cat)}</span>${item.caption}</div>`;
    tile.onclick = ()=> { lightboxItems = visibleItems; openLightbox(visibleItems.indexOf(item)); };
    return tile;
  }

  function columnCount(){
    const w = window.innerWidth;
    if(w < 640) return 1;
    if(w < 900) return 2;
    if(w < 1200) return 3;
    return 4;
  }

  function renderMasonry(container, group, indexOf){
    const wide = group.filter(item=>item.wide);
    const normal = group.filter(item=>!item.wide);

    wide.forEach(item=>{
      const isPanorama = (item.r || 0.75) < 0.4;
      if(isPanorama){
        const tile = buildTile(item, indexOf(item));
        tile.classList.add('tile-panorama');
        container.appendChild(tile);
        return;
      }
      const mainR = item.r || 0.75;
      const mainFlex = mainR > 1 ? 1.2 : 2;

      const row = document.createElement('div');
      row.className = 'wide-row';
      const main = document.createElement('div');
      main.className = 'wide-row-main';
      main.style.flex = mainFlex + ' 1 0';
      main.appendChild(buildTile(item, indexOf(item)));
      row.appendChild(main);

      const target = mainFlex * mainR;
      let sum = 0;
      const fillers = [];
      while(normal.length && fillers.length < 4){
        const nextR = normal[0].r || 0.75;
        const newSum = sum + nextR;
        if(fillers.length > 0 && Math.abs(newSum - target) >= Math.abs(sum - target)) break;
        fillers.push(normal.shift());
        sum = newSum;
      }
      if(fillers.length){
        const fill = document.createElement('div');
        fill.className = 'wide-row-fill';
        fillers.forEach(f => fill.appendChild(buildTile(f, indexOf(f))));
        row.appendChild(fill);
      }
      container.appendChild(row);
    });

    if(normal.length===0) return;
    const gridDiv = document.createElement('div');
    gridDiv.className = 'grid';
    const n = Math.min(columnCount(), normal.length);
    const cols = [];
    const colHeights = new Array(n).fill(0);
    for(let i=0;i<n;i++){
      const col = document.createElement('div');
      col.className = 'grid-col';
      cols.push(col);
      gridDiv.appendChild(col);
    }
    normal.forEach(item=>{
      let shortest = 0;
      for(let i=1;i<n;i++){
        if(colHeights[i] < colHeights[shortest]) shortest = i;
      }
      cols[shortest].appendChild(buildTile(item, indexOf(item)));
      colHeights[shortest] += (item.r || 0.75);
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
  const lbPictureWrap = document.getElementById('lbPictureWrap');
  const lbCat = document.getElementById('lbCat');
  const lbCaption = document.getElementById('lbCaption');
  const lbShareX = document.getElementById('lbShareX');
  const lbShareWa = document.getElementById('lbShareWa');
  const lbCopyLink = document.getElementById('lbCopyLink');
  let currentIdx = 0;
  let lightboxItems = [];
  let restoreHash = '';

  function openLightbox(idx){
    currentIdx = idx;
    showCurrent();
    lightbox.classList.add('open');
    lightbox.removeAttribute('aria-hidden');
    document.getElementById('lbClose').focus();
    document.addEventListener('keydown', trapFocus);
  }
  function closeLightbox(){
    lightbox.classList.remove('open');
    lightbox.setAttribute('aria-hidden', 'true');
    document.removeEventListener('keydown', trapFocus);
    if(location.hash && bySlug[location.hash.slice(1)]){
      history.replaceState(null, '', location.pathname);
    }
  }
  function trapFocus(e){
    if(e.key !== 'Tab') return;
    const focusables = lightbox.querySelectorAll('button, a[href]');
    const first = focusables[0], last = focusables[focusables.length-1];
    if(e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
    else if(!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
  }
  function showCurrent(){
    const item = lightboxItems[currentIdx];
    lbPictureWrap.innerHTML = pictureHTML(item, 'full', '', 'lb-img', 'id="lbImg"');
    lbCat.textContent = item.cat;
    lbCaption.textContent = item.caption;

    history.replaceState(null, '', '#' + item.slug);
    const shareUrl = location.origin + location.pathname + '#' + item.slug;
    const shareText = item.caption + ' — Güntay Şimşek Fotoğraf';
    lbShareX.href = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent(shareText) + '&url=' + encodeURIComponent(shareUrl);
    lbShareWa.href = 'https://wa.me/?text=' + encodeURIComponent(shareText + ' ' + shareUrl);
    lbCopyLink.dataset.url = shareUrl;
  }
  document.getElementById('lbClose').onclick = closeLightbox;
  document.getElementById('lbPrev').onclick = ()=>{ currentIdx = (currentIdx-1+lightboxItems.length)%lightboxItems.length; showCurrent(); };
  document.getElementById('lbNext').onclick = ()=>{ currentIdx = (currentIdx+1)%lightboxItems.length; showCurrent(); };
  lightbox.addEventListener('click', (e)=>{ if(e.target===lightbox) closeLightbox(); });
  document.addEventListener('keydown', (e)=>{
    if(!lightbox.classList.contains('open')) return;
    if(e.key==='Escape') closeLightbox();
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

  const MODAL_KEYS = {hakkinda:'hakkindaModal', konsept:'konseptModal', degerlendirmeler:'degerlendirmelerModal', basinda:'medyaModal'};
  const MODAL_BTNS = {hakkindaModal:'hakkindaBtn', konseptModal:'konseptBtn', degerlendirmelerModal:'degerlendirmelerBtn', medyaModal:'medyaBtn'};

  function openModal(modalId){
    const modal = document.getElementById(modalId);
    if(!modal) return;
    modal.classList.add('open');
    modal.removeAttribute('aria-hidden');
    const closeBtn = modal.querySelector('.lb-close');
    if(closeBtn) closeBtn.focus();
    const key = Object.keys(MODAL_KEYS).find(k=>MODAL_KEYS[k]===modalId);
    if(key) history.replaceState(null, '', '#' + key);
  }
  function closeModal(modal){
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    if(Object.values(MODAL_KEYS).includes(location.hash.slice(1) ? MODAL_KEYS[location.hash.slice(1)] : null) || MODAL_KEYS[location.hash.slice(1)]){
      history.replaceState(null, '', location.pathname);
    }
  }

  function wireModal(modalId, btnId, closeId){
    const modal = document.getElementById(modalId);
    const btn = document.getElementById(btnId);
    if(!modal || !btn) return;
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    const labelEl = modal.querySelector('.exhibit-label, .press-title');
    if(labelEl){
      const labelId = modalId + 'Label';
      labelEl.id = labelId;
      modal.setAttribute('aria-labelledby', labelId);
    }
    btn.setAttribute('aria-haspopup', 'dialog');
    btn.onclick = ()=> openModal(modalId);
    document.getElementById(closeId).setAttribute('aria-label', 'Kapat / Close');
    document.getElementById(closeId).onclick = ()=> closeModal(modal);
    modal.addEventListener('click', (e)=>{ if(e.target===modal) closeModal(modal); });
    document.addEventListener('keydown', (e)=>{
      if(e.key==='Escape' && modal.classList.contains('open')) closeModal(modal);
    });
  }
  wireModal('konseptModal', 'konseptBtn', 'konseptClose');
  wireModal('hakkindaModal', 'hakkindaBtn', 'hakkindaClose');
  wireModal('degerlendirmelerModal', 'degerlendirmelerBtn', 'degerlendirmelerClose');
  wireModal('medyaModal', 'medyaBtn', 'medyaClose');

  document.getElementById('lbClose').setAttribute('aria-label', 'Kapat / Close');
  document.getElementById('lbPrev').setAttribute('aria-label', 'Önceki fotoğraf / Previous photo');
  document.getElementById('lbNext').setAttribute('aria-label', 'Sonraki fotoğraf / Next photo');
  lightbox.setAttribute('role', 'dialog');
  lightbox.setAttribute('aria-modal', 'true');
  lightbox.setAttribute('aria-label', 'Fotoğraf büyütme / Photo lightbox');

  document.querySelectorAll('.series-tile, .series-hero').forEach(tile=>{
    tile.addEventListener('click', ()=>{
      const caption = tile.dataset.caption;
      const seriesItems = ITEMS.filter(i=>i.cat==='Ay ve Uçak');
      lightboxItems = seriesItems;
      const idx = seriesItems.findIndex(i=>i.caption===caption);
      openLightbox(idx===-1 ? 0 : idx);
    });
  });

  renderFilters();
  renderGrid();

  // Deep-link on load: #<photo-slug> opens the lightbox, #<modal-key> opens a modal
  const initialHash = location.hash.slice(1);
  if(initialHash){
    if(bySlug[initialHash]){
      lightboxItems = ITEMS;
      openLightbox(ITEMS.indexOf(bySlug[initialHash]));
    } else if(MODAL_KEYS[initialHash]){
      openModal(MODAL_KEYS[initialHash]);
    }
  }
}

loadPhotos().then(init).catch(err=>{
  document.getElementById('grid').innerHTML = '<p class="empty-state">Fotoğraflar yüklenemedi.</p>';
  console.error(err);
});
