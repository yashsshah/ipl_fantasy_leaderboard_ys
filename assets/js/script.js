document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(button => button.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(panel => panel.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(btn.dataset.tab).classList.add('active');
    });
});

const leaderboardBody = document.getElementById('leaderboard-body');
const matchList = document.getElementById('match-list');
const prizeList = document.getElementById('player-prizes-list');
const bonusPrizeList = document.getElementById('bonus-prizes-list');
const lastSyncedValue = document.getElementById('last-synced-value');
const latestResultTitle = document.getElementById('latest-result-title');
const latestResultSummary = document.getElementById('latest-result-summary');
const latestResultWinner = document.getElementById('latest-result-winner');
const latestResultScore = document.getElementById('latest-result-score');
const latestResultPrize = document.getElementById('latest-result-prize');
const membersGrid = document.getElementById('members-grid');
const memberStats = document.getElementById('member-stats');
const participantsBody = document.getElementById('participants-body');
const scheduleBody = document.getElementById('schedule-body');
const scoresHead = document.getElementById('scores-head');
const scoresBody = document.getElementById('scores-body');
const tableRankingsBody = document.getElementById('table-rankings-body');
const predictionsHead = document.getElementById('predictions-head');
const predictionsBody = document.getElementById('predictions-body');
const prizesBody = document.getElementById('prizes-body');
const overallLeaderboardPrizes = [70, 40, 20];

function normalizeName(value) {
    return (value || '').trim().toLowerCase();
}

function hexToRgb(hexColor) {
    const normalized = hexColor.replace('#', '');
    const value = normalized.length === 3
        ? normalized.split('').map(char => char + char).join('')
        : normalized;
    const red = Number.parseInt(value.slice(0, 2), 16);
    const green = Number.parseInt(value.slice(2, 4), 16);
    const blue = Number.parseInt(value.slice(4, 6), 16);
    return `${red}, ${green}, ${blue}`;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function formatPoints(value) {
    return value === null || value === undefined || value === '' ? 'TBD' : `${value} pts`;
}

function formatCompactPoints(value) {
    return value === null || value === undefined || value === '' ? '-' : `${value}`;
}

function formatCurrency(value) {
    return value === null || value === undefined || value === '' ? '-' : `$${value}`;
}

function formatTimestamp(value) {
    if (!value) {
        return 'unknown';
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return escapeHtml(value);
    }

    return parsed.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

function formatText(value, fallback = '-') {
    return value === null || value === undefined || value === '' ? fallback : escapeHtml(value);
}

function buildMemberLookup(members) {
    return new Map((members || []).map(member => [normalizeName(member.name), member]));
}

function getMemberMeta(name, memberLookup) {
    return memberLookup.get(normalizeName(name)) || null;
}

function splitCombinedValue(value) {
    if (!value) {
        return [];
    }
    return String(value).split(' / ').map(item => item.trim()).filter(Boolean);
}

function renderNamedPerson(name, memberLookup) {
    const safeName = escapeHtml(name || 'TBD');
    const member = getMemberMeta(name, memberLookup);

    if (!member) {
        return `<span class="person-label">${safeName}</span>`;
    }

    const teamColor = member.color || '#94a3b8';
    return `<span class="person-label" style="--person-color: ${teamColor}; --person-color-rgb: ${hexToRgb(teamColor)};">${safeName}</span>`;
}

function renderMultiplePeople(namesValue, memberLookup) {
    const names = splitCombinedValue(namesValue);
    if (!names.length) {
        return '<span class="person-label person-label-muted">Awaiting result</span>';
    }

    return names
        .map(name => renderNamedPerson(name, memberLookup))
        .join('<span class="inline-separator">/</span>');
}

function renderLeaderboardPerson(name, teamName, memberLookup) {
    const nameMarkup = renderNamedPerson(name, memberLookup);
    if (!teamName) {
        return nameMarkup;
    }
    return `${nameMarkup} <span class="leaderboard-team-name">(${escapeHtml(teamName)})</span>`;
}

function getLeaderboardRows(data) {
    if (Array.isArray(data.leaderboard) && data.leaderboard.length) {
        return data.leaderboard;
    }
    return (data.players || []).map((player, index) => ({
        rank: index + 1,
        leagueMemberName: player.name,
        leagueTeamName: getMemberMeta(player.name, buildMemberLookup(data.leagueMembers || []))?.teamName || null,
        totalPoints: player.totalPoints,
    }));
}

function getMatchWinnerRows(data) {
    if (Array.isArray(data.matchDayWinners) && data.matchDayWinners.length) {
        return data.matchDayWinners;
    }
    return (data.matches || []).map(match => ({
        matchNum: match.match,
        matchDetails: match.matchDetails || `Match ${match.match}`,
        leagueMemberName: match.winner || null,
        leagueTeamName: match.winnerTeamName || null,
        score: match.points,
        prizeAmount: match.amount,
    }));
}

function getCompletedMatchWinnerRows(data) {
    return getMatchWinnerRows(data).filter(match => match.score !== null && match.score !== undefined && match.score !== '');
}

function getPlayerPrizeRows(data) {
    if (Array.isArray(data.playerBasedPrizes) && data.playerBasedPrizes.length) {
        return data.playerBasedPrizes;
    }
    return (data.playerPrizes || []).map(prize => ({
        prizeName: prize.prize,
        playerName: prize.player,
        pointsScored: prize.points,
        matchDetails: prize.matchDetails,
        prizeAmount: prize.amount,
    }));
}

function clearRenderedData() {
    leaderboardBody.innerHTML = '';
    matchList.innerHTML = '';
    prizeList.innerHTML = '';
    bonusPrizeList.innerHTML = '';
    membersGrid.innerHTML = '';
    memberStats.innerHTML = '';
    participantsBody.innerHTML = '';
    scheduleBody.innerHTML = '';
    scoresHead.innerHTML = '';
    scoresBody.innerHTML = '';
    tableRankingsBody.innerHTML = '';
    predictionsHead.innerHTML = '';
    predictionsBody.innerHTML = '';
    prizesBody.innerHTML = '';
}

function renderSyncStatus(data) {
    lastSyncedValue.textContent = formatTimestamp(data.meta?.lastSyncedAt);
}

function renderLeaderboard(data, memberLookup) {
    getLeaderboardRows(data).forEach((player, index) => {
        const row = document.createElement('tr');
        const rankIcons = ['🥇', '🥈', '🥉'];
        const rankDisplay = index < 3 ? rankIcons[index] : player.rank || index + 1;
        const overallPrize = overallLeaderboardPrizes[index] ?? null;
        const pointsLabel = player.totalPoints === null || player.totalPoints === undefined || player.totalPoints === ''
            ? 'TBD'
            : `${player.totalPoints} pts`;
        row.innerHTML = `
            <td class="rank-col">${rankDisplay}</td>
            <td>${renderLeaderboardPerson(player.leagueMemberName, player.leagueTeamName, memberLookup)}</td>
            <td><span class="stat-pill leaderboard-pill"><strong>${pointsLabel}</strong></span></td>
            <td><span class="stat-pill stat-pill-money leaderboard-pill">${overallPrize ? formatCurrency(overallPrize) : '-'}</span></td>
        `;
        leaderboardBody.appendChild(row);
    });
}

function renderMatchWinners(data, memberLookup) {
    const completedMatches = getCompletedMatchWinnerRows(data)
        .slice()
        .sort((left, right) => Number(right.matchNum || 0) - Number(left.matchNum || 0));

    const latestMatch = completedMatches[0] || null;
    renderLatestResult(latestMatch, memberLookup);

    completedMatches.slice(0, 12).forEach(match => {
        const item = document.createElement('li');
        item.className = 'result-item';
        const lockMarkup = match.prizeAmount ? '<span class="match-lock-icon" aria-label="locked prize"><i class="fas fa-lock"></i></span>' : '';
        item.innerHTML = `
            <div class="result-content">
                <div class="result-copy">
                    <div class="result-eyebrow">Match ${escapeHtml(match.matchNum)}</div>
                    <div class="result-title-row">
                        <div class="result-title">${formatText(match.matchDetails, 'Awaiting fixture')}</div>
                        ${lockMarkup}
                    </div>
                    <div class="result-subtitle">${renderMultiplePeople(match.leagueMemberName, memberLookup)}</div>
                </div>
                <div class="result-metrics">
                    <span class="stat-pill">${formatPoints(match.score)}</span>
                    <span class="stat-pill stat-pill-money">${formatCurrency(match.prizeAmount)}</span>
                </div>
            </div>
        `;
        matchList.appendChild(item);
    });

    if (!completedMatches.length) {
        const item = document.createElement('li');
        item.innerHTML = '<i class="fas fa-hourglass-half"></i> <strong>No completed matches yet.</strong> Results will appear here as scores are added.';
        matchList.appendChild(item);
    }
}

function renderLatestResult(match, memberLookup) {
    if (!match) {
        latestResultTitle.innerHTML = '<i class="fas fa-bolt"></i> Awaiting first completed result';
        latestResultSummary.textContent = 'Match winners will appear here as soon as scores are available.';
        latestResultWinner.textContent = 'TBD';
        latestResultScore.textContent = '-';
        latestResultPrize.textContent = '-';
        return;
    }

    latestResultTitle.innerHTML = `<i class="fas fa-bolt"></i> Match ${escapeHtml(match.matchNum)} • ${escapeHtml(match.matchDetails || 'Result')}`;
    latestResultSummary.textContent = 'Most recent completed fixture and prize split.';
    latestResultWinner.innerHTML = renderMultiplePeople(match.leagueMemberName, memberLookup);
    latestResultScore.textContent = formatCompactPoints(match.score);
    latestResultPrize.textContent = formatCurrency(match.prizeAmount);
}

function renderPlayerPrizes(data, memberLookup) {
    getPlayerPrizeRows(data).forEach(prize => {
        const item = document.createElement('li');
        item.className = 'result-item';
        item.innerHTML = `
            <div class="result-content">
                <div class="result-copy">
                    <div class="result-eyebrow">Player-based Prize</div>
                    <div class="result-title">${escapeHtml(prize.prizeName)}</div>
                    <div class="result-subtitle">${formatText(prize.playerName, 'TBD')}</div>
                </div>
                <div class="result-metrics">
                    <span class="stat-pill">${formatPoints(prize.pointsScored)}</span>
                    <span class="stat-pill stat-pill-money">${formatCurrency(prize.prizeAmount)}</span>
                </div>
            </div>
        `;
        prizeList.appendChild(item);
    });
}

function renderBonusPrizes(data, memberLookup) {
    (data.bonusPrizes || []).forEach(prize => {
        const item = document.createElement('li');
        item.className = 'result-item';
        item.innerHTML = `
            <div class="result-content">
                <div class="result-copy">
                    <div class="result-eyebrow">Bonus Prize</div>
                    <div class="result-title">${escapeHtml(prize.prizeName)}</div>
                    <div class="result-subtitle">${renderMultiplePeople(prize.leagueMemberName, memberLookup)}</div>
                </div>
                <div class="result-metrics">
                    <span class="stat-pill">${formatPoints(prize.score)}</span>
                    <span class="stat-pill stat-pill-money">${formatCurrency(prize.prizeAmount)}</span>
                </div>
            </div>
        `;
        bonusPrizeList.appendChild(item);
    });
}

function renderMemberStats(data) {
    const participants = data.participants || [];
    const paidCount = participants.filter(participant => participant.paymentStatus).length;
    const totalBuyIn = participants.reduce((sum, participant) => sum + (participant.buyInAmount || 0), 0);
    const completedMatches = getMatchWinnerRows(data).filter(match => match.score !== null && match.score !== undefined && match.score !== '').length;
    const stats = [
        { label: 'League Members', value: participants.length },
        { label: 'Payments Logged', value: paidCount },
        { label: 'Total Buy-in', value: formatCurrency(totalBuyIn) },
        { label: 'Completed Matches', value: completedMatches },
    ];

    stats.forEach(stat => {
        const card = document.createElement('div');
        card.className = 'mini-stat';
        card.innerHTML = `<div class="mini-stat-value">${escapeHtml(stat.value)}</div><div class="mini-stat-label">${escapeHtml(stat.label)}</div>`;
        memberStats.appendChild(card);
    });
}

function renderMembers(data, memberLookup) {
    (data.leagueMembers || []).forEach((member, index) => {
        const card = document.createElement('div');
        const teamColor = member.color || '#94a3b8';
        const teamName = member.teamName || 'No team set';
        card.className = 'member-card';
        card.style.setProperty('--team-color', teamColor);
        card.style.setProperty('--team-color-rgb', hexToRgb(teamColor));
        card.innerHTML = `
            <div class="member-rank">${index + 1}</div>
            <div class="member-avatar">${escapeHtml(member.name.charAt(0).toUpperCase())}</div>
            <div class="member-info">
                <div class="member-name">${escapeHtml(member.name)}</div>
                <div class="member-team"><i class="fas fa-shield-halved"></i> ${escapeHtml(teamName)}</div>
                <div class="member-team-accent">
                    <span class="team-swatch"></span>
                    <span class="team-label">${escapeHtml(teamName)}</span>
                </div>
            </div>
        `;
        membersGrid.appendChild(card);
    });

    (data.participants || []).forEach(participant => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${formatText(participant.leagueMemberNum)}</td>
            <td>${renderLeaderboardPerson(participant.leagueMemberName, participant.leagueTeamName, memberLookup)}</td>
            <td>${formatText(participant.leagueTeamName)}</td>
            <td>${renderStatusChip(participant.joinedStatus)}</td>
            <td>${renderStatusChip(participant.paymentStatus)}</td>
            <td>${formatCurrency(participant.buyInAmount)}</td>
            <td>${formatText(participant.email)}</td>
        `;
        participantsBody.appendChild(row);
    });
}

function renderStatusChip(value) {
    const label = value || 'Pending';
    const modifier = value ? 'is-active' : 'is-muted';
    return `<span class="status-chip ${modifier}">${escapeHtml(label)}</span>`;
}

function renderSchedule(data, memberLookup) {
    const winnerRows = getMatchWinnerRows(data);
    const winnerLookup = new Map(winnerRows.map(row => [Number(row.matchNum), row]));
    const latestCompletedMatchNum = getCompletedMatchWinnerRows(data)
        .reduce((latest, match) => Math.max(latest, Number(match.matchNum) || 0), 0);

    (data.matchSchedule || []).forEach(match => {
        const winner = winnerLookup.get(Number(match.matchNum));
        const row = document.createElement('tr');
        const isLatestCompleted = latestCompletedMatchNum !== 0 && Number(match.matchNum) === latestCompletedMatchNum;
        if (isLatestCompleted) {
            row.classList.add('schedule-row-latest');
        }
        row.innerHTML = `
            <td>${formatText(match.matchNum)}</td>
            <td>${formatText(match.matchDate)}</td>
            <td>${formatText(match.matchTimeIST)}</td>
            <td>
                <div class="fixture-cell">
                    <strong>${formatText(match.homeTeamName)}</strong>
                    <span class="fixture-vs">vs</span>
                    <strong>${formatText(match.awayTeamName)}</strong>
                </div>
                <div class="fixture-meta">${formatText(winner?.matchDetails)}${isLatestCompleted ? ' <span class="fixture-highlight">Latest completed match</span>' : ''}</div>
            </td>
            <td>${formatText(match.venue)}</td>
            <td>${renderMultiplePeople(winner?.leagueMemberName, memberLookup)}</td>
            <td>${formatCurrency(winner?.prizeAmount)}</td>
        `;
        scheduleBody.appendChild(row);
    });
}

function renderScoreMatrix(data) {
    const rows = data.matchDayScores || [];
    const memberNames = data.leagueMembers?.map(member => member.name) || [];
    scoresHead.innerHTML = `<tr><th>Match</th><th>Fixture</th>${memberNames.map(name => `<th>${escapeHtml(name)}</th>`).join('')}</tr>`;

    rows.forEach(match => {
        const scoreValues = memberNames
            .map(name => match.scores?.[name])
            .filter(value => value !== null && value !== undefined && value !== '');
        const maxScore = scoreValues.length ? Math.max(...scoreValues) : null;
        const row = document.createElement('tr');
        const cells = memberNames.map(name => {
            const value = match.scores?.[name];
            const isTop = maxScore !== null && value === maxScore;
            return `<td class="${isTop ? 'score-cell is-top-score' : 'score-cell'}">${formatCompactPoints(value)}</td>`;
        }).join('');
        row.innerHTML = `<td>${formatText(match.matchNum)}</td><td>${formatText(match.matchDetails)}</td>${cells}`;
        scoresBody.appendChild(row);
    });
}

function renderTableTracker(data) {
    (data.tableRankings || []).forEach(rowData => {
        const row = document.createElement('tr');
        row.innerHTML = `<td>${formatText(rowData.rank)}</td><td>${formatText(rowData.iplTeamName)}</td>`;
        tableRankingsBody.appendChild(row);
    });

    const memberNames = data.leagueMembers?.map(member => member.name) || [];
    predictionsHead.innerHTML = `<tr><th>Rank</th>${memberNames.map(name => `<th>${escapeHtml(name)}</th>`).join('')}</tr>`;

    (data.tablePredictions || []).forEach(prediction => {
        const row = document.createElement('tr');
        const cells = memberNames.map(name => `<td>${formatText(prediction.predictions?.[name])}</td>`).join('');
        row.innerHTML = `<td>${formatText(prediction.rank)}</td>${cells}`;
        predictionsBody.appendChild(row);
    });
}

function renderPrizePool(data) {
    (data.prizesList || []).forEach(prize => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${formatText(prize.prizeName)}</td>
            <td>${formatCurrency(prize.prizeAmount)}</td>
            <td>${formatText(prize.prizeCount)}</td>
            <td>${formatCurrency(prize.prizeTotalAmount)}</td>
        `;
        prizesBody.appendChild(row);
    });
}

function renderData(data) {
    clearRenderedData();
    const memberLookup = buildMemberLookup(data.leagueMembers || []);
    renderSyncStatus(data);
    renderLeaderboard(data, memberLookup);
    renderMatchWinners(data, memberLookup);
    renderPlayerPrizes(data, memberLookup);
    renderBonusPrizes(data, memberLookup);
    renderMemberStats(data);
    renderMembers(data, memberLookup);
    renderSchedule(data, memberLookup);
    renderScoreMatrix(data);
    renderTableTracker(data);
    renderPrizePool(data);
}

async function loadLeagueData() {
    const response = await fetch(`data.json?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) {
        throw new Error(`Failed to load data.json: ${response.status}`);
    }
    const data = await response.json();
    renderData(data);
}

loadLeagueData().catch(err => console.error('Error loading data:', err));
window.setInterval(() => {
    loadLeagueData().catch(err => console.error('Error loading data:', err));
}, 30000);