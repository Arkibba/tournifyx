// HTML bracket renderer
const POLL_INTERVAL = 2500;

async function fetchStages(tournamentId) {
  const res = await fetch(`/tournament/${tournamentId}/knockout-json/`, {credentials: 'same-origin'});
  return res.json();
}

function clearContainer(c) { c.innerHTML = ''; }

function createMatchCard(m) {
  const card = document.createElement('div');
  card.className = 'match-card';
  if (!m.winner_name) card.classList.add('pending');
  const inner = document.createElement('div');
  inner.className = 'match-players';

  const p1 = document.createElement('div');
  p1.innerHTML = `<div class="player-name">${m.player1}</div>` + (m.player2? '' : `<div class="player-sub">vs</div>`);
  inner.appendChild(p1);

  const p2 = document.createElement('div');
  p2.innerHTML = `<div class="player-sub">${m.player2 ? m.player2 : 'BYE'}</div>`;
  inner.appendChild(p2);

  card.appendChild(inner);
  if (m.winner_name) {
    // Inline winner text for better visibility (not clipped by absolute positioning)
    const winLine = document.createElement('div');
    winLine.className = 'winner-line';
    winLine.textContent = `Winner is ${m.winner_name}`;
    card.appendChild(winLine);
  }
  return card;
}

function renderHtmlBracket(container, stages) {
  clearContainer(container);
  if (!stages || stages.length === 0) {
    container.innerHTML = '<div class="text-gray-400">No bracket yet.</div>';
    return;
  }

  const grid = document.createElement('div');
  grid.className = 'bracket-grid';

  stages.forEach(stage => {
    const col = document.createElement('div');
    col.className = 'bracket-column';
    const header = document.createElement('div');
    header.className = 'bracket-header';
    header.textContent = stage.label;
    col.appendChild(header);

    stage.matches.forEach(m => {
      const card = createMatchCard(m);
      col.appendChild(card);
    });
    grid.appendChild(col);
  });

  container.appendChild(grid);
}

function startBracket(tournamentId) {
  const container = document.getElementById('bracket-container');
  if (!container) return;

  let lastJson = null;

  async function poll() {
    try {
      const data = await fetchStages(tournamentId);
      const stages = data.stages || [];
      const jsonStr = JSON.stringify(stages);
      if (jsonStr !== lastJson) {
        renderHtmlBracket(container, stages);
        lastJson = jsonStr;
      }
    } catch (err) {
      console.error('Bracket fetch error', err);
    }
    setTimeout(poll, POLL_INTERVAL);
  }
  poll();
}

window.startBracket = startBracket;
