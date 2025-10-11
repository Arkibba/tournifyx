// Lightweight client-side table sorting with URL param persistence and aria-sort updates
(function(){
  function parseNumber(s){ return Number((s||'').toString().replace(/[^0-9.-]/g,'')) || 0; }

  function getParam(key){ const url = new URL(window.location); return url.searchParams.get(key); }
  function setParam(key,val){ const url = new URL(window.location); if(val===null) url.searchParams.delete(key); else url.searchParams.set(key,val); history.replaceState(null,'',url); }

  function init(){
    const table = document.getElementById('playersTable');
    if(!table) return;
    const headers = table.querySelectorAll('thead th.sortable');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr')).filter(r=>!r.classList.contains('empty'));

    // restore sort from URL
    const sortKey = getParam('sort');
    const sortDir = getParam('dir') || 'desc';

    headers.forEach((th, idx)=>{
      const index = parseInt(th.dataset.index,10);
      th.addEventListener('click', ()=>{ sortBy(index, th.dataset.type || 'text', th); });
    });

    if(sortKey){
      const target = Array.from(headers).find(h=>h.dataset.index === sortKey);
      if(target) sortBy(parseInt(target.dataset.index,10), target.dataset.type, target, sortDir);
    }

    function sortBy(colIndex, type, thElem, direction){
      const dir = direction || (thElem.classList.contains('sorted-asc') ? 'desc' : 'asc');
      // remove sort classes
      headers.forEach(h=>h.classList.remove('sorted-asc','sorted-desc'));
      thElem.classList.add(dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
      // sort rows
      const sorted = rows.slice().sort((a,b)=>{
        const aCell = a.children[colIndex];
        const bCell = b.children[colIndex];
        if(type==='number'){
          return dir === 'asc' ? parseNumber(aCell.dataset.value) - parseNumber(bCell.dataset.value) : parseNumber(bCell.dataset.value) - parseNumber(aCell.dataset.value);
        }
        // text
        const aText = (aCell.textContent||'').trim().toLowerCase();
        const bText = (bCell.textContent||'').trim().toLowerCase();
        if(aText < bText) return dir === 'asc' ? -1 : 1;
        if(aText > bText) return dir === 'asc' ? 1 : -1;
        return 0;
      });
      // reattach
      sorted.forEach(r=>tbody.appendChild(r));
      // update URL params
      setParam('sort', String(colIndex));
      setParam('dir', dir);
      // update aria-sort
      headers.forEach(h=>h.setAttribute('aria-sort','none'));
      thElem.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
