document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(button => button.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(panel => panel.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(btn.dataset.tab).classList.add('active');
    });
});

document.addEventListener('click', event => {
    const toggle = event.target.closest('.section-toggle');
    if (!toggle) {
        return;
    }

    const section = toggle.closest('.collapsible-section');
    if (!section) {
        return;
    }

    const isExpanded = toggle.getAttribute('aria-expanded') !== 'false';
    toggle.setAttribute('aria-expanded', String(!isExpanded));
    section.classList.toggle('is-collapsed', isExpanded);

    if (section.classList.contains('collapsible-left-section')) {
        const trackerLayout = section.closest('.table-tracker-layout');
        if (trackerLayout) {
            trackerLayout.classList.toggle('has-collapsed-left-rail', isExpanded);
        }
    }

    if (section.classList.contains('collapsible-right-section')) {
        const trackerLayout = section.closest('.table-tracker-layout');
        if (trackerLayout) {
            trackerLayout.classList.toggle('has-collapsed-right-rail', isExpanded);
        }
    }
});

const leaderboardBody = document.getElementById('leaderboard-body');
const matchList = document.getElementById('match-list');
const prizeList = document.getElementById('player-prizes-list');
const bonusPrizeList = document.getElementById('bonus-prizes-list');
const lastSyncedValue = document.getElementById('last-synced-value');
const membersGrid = document.getElementById('members-grid');
const memberStats = document.getElementById('member-stats');
const memberPrizeBreakdown = document.getElementById('member-prize-breakdown');
const prizeBreakdownName = document.getElementById('prize-breakdown-name');
const prizeBreakdownSubtitle = document.getElementById('prize-breakdown-subtitle');
const prizeBreakdownTotal = document.getElementById('prize-breakdown-total');
const prizeBreakdownBody = document.getElementById('prize-breakdown-body');
const participantsBody = document.getElementById('participants-body');
const scheduleBody = document.getElementById('schedule-body');
const scoresHead = document.getElementById('scores-head');
const scoresBody = document.getElementById('scores-body');
const scoresTable = document.getElementById('scores-table');
const scoresTableWrapper = document.getElementById('scores-table-wrapper');
const scoresTopScrollbar = document.getElementById('scores-top-scrollbar');
const scoresTopScrollbarSpacer = document.getElementById('scores-top-scrollbar-spacer');
const scoresMemberFocus = document.getElementById('scores-member-focus');
const tableRankingsBody = document.getElementById('table-rankings-body');
const predictionsHead = document.getElementById('predictions-head');
const predictionsBody = document.getElementById('predictions-body');
const prizesBody = document.getElementById('prizes-body');
let currentPrizeSummaryLookup = new Map();
let syncingScoreScroll = false;

function updateScoresTopScrollbar() {
    if (!scoresTableWrapper || !scoresTopScrollbarSpacer) {
        return;
    }
    scoresTopScrollbarSpacer.style.width = `${scoresTableWrapper.scrollWidth}px`;
}

function syncScoresScroll(source, target) {
    if (!source || !target || syncingScoreScroll) {
        return;
    }
    syncingScoreScroll = true;
    target.scrollLeft = source.scrollLeft;
    window.requestAnimationFrame(() => {
        syncingScoreScroll = false;
    });
}

function setFocusedScoreColumn(memberName) {
    const normalizedTarget = normalizeName(memberName);
    document.querySelectorAll('[data-score-column]').forEach(cell => {
        const isFocused = normalizedTarget && normalizeName(cell.dataset.scoreColumn) === normalizedTarget;
        cell.classList.toggle('is-focused-score-column', Boolean(isFocused));
    });

    if (!normalizedTarget || !scoresTableWrapper) {
        return;
    }

    const targetHeader = scoresHead.querySelector(`th[data-score-column="${memberName}"]`)
        || Array.from(scoresHead.querySelectorAll('[data-score-column]')).find(cell => normalizeName(cell.dataset.scoreColumn) === normalizedTarget);

    if (!targetHeader) {
        return;
    }

    const leftPadding = 24;
    const targetLeft = targetHeader.offsetLeft - leftPadding;
    scoresTableWrapper.scrollTo({ left: Math.max(targetLeft, 0), behavior: 'smooth' });
    if (scoresTopScrollbar) {
        scoresTopScrollbar.scrollTo({ left: Math.max(targetLeft, 0), behavior: 'smooth' });
    }
}

function populateScoresMemberFocus(memberNames) {
    if (!scoresMemberFocus) {
        return;
    }

    const currentValue = scoresMemberFocus.value;
    const options = ['<option value="">All members</option>']
        .concat(memberNames.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`));
    scoresMemberFocus.innerHTML = options.join('');

    if (memberNames.includes(currentValue)) {
        scoresMemberFocus.value = currentValue;
    }
}

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

function titleCasePrizeType(value) {
    return String(value || '')
        .split('-')
        .filter(Boolean)
        .map(token => token.charAt(0).toUpperCase() + token.slice(1))
        .join(' ');
}

function buildMemberLookup(members) {
    return new Map((members || []).map(member => [normalizeName(member.name), member]));
}

function buildPrizeSummaryLookup(summaryRows) {
    return new Map((summaryRows || []).map(row => [normalizeName(row.leagueMemberName), row]));
}

const overallLeaderboardPrizes = [70, 40, 20];

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
    return data.playerBasedPrizes || [];
}

function clearRenderedData() {
    leaderboardBody.innerHTML = '';
    matchList.innerHTML = '';
    prizeList.innerHTML = '';
    bonusPrizeList.innerHTML = '';
    membersGrid.innerHTML = '';
    memberStats.innerHTML = '';
    memberPrizeBreakdown.classList.add('is-hidden');
    prizeBreakdownName.textContent = 'Select a member';
    prizeBreakdownSubtitle.textContent = 'Click a member row above to inspect the full breakdown.';
    prizeBreakdownTotal.textContent = '-';
    prizeBreakdownBody.innerHTML = '';
    participantsBody.innerHTML = '';
    scheduleBody.innerHTML = '';
    scoresHead.innerHTML = '';
    scoresBody.innerHTML = '';
    if (scoresMemberFocus) {
        scoresMemberFocus.value = '';
    }
    tableRankingsBody.innerHTML = '';
    predictionsHead.innerHTML = '';
    predictionsBody.innerHTML = '';
    prizesBody.innerHTML = '';
}

function renderPrizeBreakdownSection(title, breakdownItems, totalAmount, isLocked) {
    const emptyMessage = `No ${title.toLowerCase()} prize entries for this member yet.`;
    const itemsMarkup = breakdownItems.length
        ? breakdownItems.map(item => {
            const meta = [];
            if (item.matchNum !== null && item.matchNum !== undefined && item.matchNum !== '') {
                meta.push(`Match ${escapeHtml(item.matchNum)}`);
            }
            if (item.matchDetails) {
                meta.push(escapeHtml(item.matchDetails));
            }

            return `
                <article class="breakdown-item">
                    <div class="breakdown-copy">
                        <div class="breakdown-title-row">
                            <h3>${escapeHtml(item.label || 'Prize entry')}</h3>
                            <span class="breakdown-type-chip">${escapeHtml(titleCasePrizeType(item.prizeType) || 'Prize')}</span>
                        </div>
                        <p class="breakdown-meta">${meta.length ? meta.join(' • ') : 'No additional details'}</p>
                    </div>
                    <div class="breakdown-amount-wrap">
                        <span class="stat-pill ${isLocked ? 'stat-pill-money' : 'stat-pill-potential'} breakdown-amount-pill">${formatCurrency(item.amount)}</span>
                        <i class="fas ${isLocked ? 'fa-lock' : 'fa-hourglass-half'} breakdown-amount-icon"></i>
                    </div>
                </article>
            `;
        }).join('')
        : `<div class="breakdown-empty">${emptyMessage}</div>`;

    return `
        <section class="breakdown-section">
            <div class="breakdown-section-header">
                <div class="breakdown-section-title-wrap">
                    <h3 class="breakdown-section-title">${title}</h3>
                    <p class="breakdown-section-copy">${isLocked ? 'Locked prizes are secured and already earned.' : 'Potential prizes reflect current leaderboard and bonus positions, so they can still change.'}</p>
                </div>
                <div class="breakdown-amount-wrap">
                    <span class="stat-pill ${isLocked ? 'stat-pill-money' : 'stat-pill-potential'} breakdown-amount-pill">${title} ${formatCurrency(totalAmount)}</span>
                    <i class="fas ${isLocked ? 'fa-lock' : 'fa-hourglass-half'} breakdown-amount-icon"></i>
                </div>
            </div>
            <div class="breakdown-section-items">${itemsMarkup}</div>
        </section>
    `;
}

function renderPrizeBreakdown(summary) {
    const lockedBreakdown = summary.lockedBreakdown || [];
    const potentialBreakdown = summary.potentialBreakdown || [];
    memberPrizeBreakdown.classList.remove('is-hidden');
    prizeBreakdownName.textContent = summary.leagueMemberName || 'Unknown member';
    prizeBreakdownSubtitle.textContent = 'Locked prizes are listed first, followed by potential prizes.';
    prizeBreakdownTotal.innerHTML = `
        <span class="stat-pill stat-pill-money breakdown-total-pill">Locked ${formatCurrency(summary.lockedPrizeAmount ?? 0)}</span>
        <i class="fas fa-lock breakdown-total-icon"></i>
        <span class="stat-pill stat-pill-potential breakdown-total-pill">Potential ${formatCurrency(summary.potentialPrizeAmount ?? 0)}</span>
        <i class="fas fa-hourglass-half breakdown-total-icon"></i>
    `;

    prizeBreakdownBody.innerHTML = [
        renderPrizeBreakdownSection('Locked', lockedBreakdown, summary.lockedPrizeAmount ?? 0, true),
        renderPrizeBreakdownSection('Potential', potentialBreakdown, summary.potentialPrizeAmount ?? 0, false),
    ].join('');

    memberPrizeBreakdown.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderSyncStatus(data) {
    lastSyncedValue.textContent = formatTimestamp(data.meta?.lastSyncedAt);
}

function renderLeaderboard(data, memberLookup, prizeSummaryLookup) {
    getLeaderboardRows(data).forEach((player, index) => {
        const row = document.createElement('tr');
        const rankIcons = ['🥇', '🥈', '🥉'];
        const rankDisplay = index < 3 ? rankIcons[index] : player.rank || index + 1;
        const pointsLabel = player.totalPoints === null || player.totalPoints === undefined || player.totalPoints === ''
            ? 'TBD'
            : `${player.totalPoints} pts`;
        const prizeSummary = prizeSummaryLookup.get(normalizeName(player.leagueMemberName)) || null;
        const potentialPrizeAmount = prizeSummary?.potentialOverallPrizeAmount ?? 0;
        const prizeCellMarkup = index < 3 && potentialPrizeAmount
            ? `<span class="leaderboard-prize-wrap"><span class="stat-pill stat-pill-money leaderboard-pill">${formatCurrency(overallLeaderboardPrizes[index])}</span><i class="fas fa-hourglass-half leaderboard-prize-icon"></i></span>`
            : '';
        row.innerHTML = `
            <td class="rank-col">${rankDisplay}</td>
            <td>${renderLeaderboardPerson(player.leagueMemberName, player.leagueTeamName, memberLookup)}</td>
            <td><span class="stat-pill leaderboard-pill"><strong>${pointsLabel}</strong></span></td>
            <td>${prizeCellMarkup}</td>
        `;
        leaderboardBody.appendChild(row);
    });
}

function renderMatchWinners(data, memberLookup) {
    const completedMatches = getCompletedMatchWinnerRows(data)
        .slice()
        .sort((left, right) => Number(right.matchNum || 0) - Number(left.matchNum || 0));

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
                    </div>
                    <div class="result-subtitle">${renderMultiplePeople(match.leagueMemberName, memberLookup)}</div>
                </div>
                <div class="result-metrics">
                    <span class="stat-pill">${formatPoints(match.score)}</span>
                    <span class="stat-pill stat-pill-money">${formatCurrency(match.prizeAmount)}</span>
                    ${lockMarkup}
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

function renderMembers(data, memberLookup, prizeSummaryLookup) {
    const sortedMembers = [...(data.leagueMembers || [])].sort((left, right) => {
        const leftSummary = prizeSummaryLookup.get(normalizeName(left.name)) || null;
        const rightSummary = prizeSummaryLookup.get(normalizeName(right.name)) || null;
        const lockedDelta = (rightSummary?.lockedPrizeAmount ?? 0) - (leftSummary?.lockedPrizeAmount ?? 0);
        if (lockedDelta !== 0) {
            return lockedDelta;
        }

        const potentialDelta = (rightSummary?.potentialPrizeAmount ?? 0) - (leftSummary?.potentialPrizeAmount ?? 0);
        if (potentialDelta !== 0) {
            return potentialDelta;
        }

        return (left.name || '').localeCompare(right.name || '');
    });

    sortedMembers.forEach((member, index) => {
        const row = document.createElement('tr');
        const teamColor = member.color || '#94a3b8';
        const teamName = member.teamName || 'No team set';
        const prizeSummary = prizeSummaryLookup.get(normalizeName(member.name)) || null;
        const lockedPrizeAmount = prizeSummary?.lockedPrizeAmount ?? 0;
        const potentialPrizeAmount = prizeSummary?.potentialPrizeAmount ?? 0;
        row.className = 'member-row';
        row.dataset.memberName = member.name;
        row.style.setProperty('--team-color', teamColor);
        row.style.setProperty('--team-color-rgb', hexToRgb(teamColor));
        row.innerHTML = `
            <td class="rank-col">${index + 1}</td>
            <td>
                <div class="member-row-name">
                    <span class="member-row-dot" aria-hidden="true"></span>
                    <span>${escapeHtml(member.name)}</span>
                </div>
            </td>
            <td>${escapeHtml(teamName)}</td>
            <td><span class="stat-pill stat-pill-money member-prize-pill">${formatCurrency(lockedPrizeAmount)}</span></td>
            <td><span class="stat-pill stat-pill-potential member-prize-pill">${formatCurrency(potentialPrizeAmount)}</span></td>
        `;
        membersGrid.appendChild(row);
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
        `;
        participantsBody.appendChild(row);
    });
}

membersGrid.addEventListener('click', event => {
    const row = event.target.closest('.member-row');
    if (!row) {
        return;
    }

    const memberName = row.dataset.memberName || '';
    const summary = currentPrizeSummaryLookup.get(normalizeName(memberName));
    if (!summary) {
        return;
    }

    document.querySelectorAll('.member-row').forEach(memberRow => {
        memberRow.classList.toggle('is-selected', memberRow.dataset.memberName === memberName);
    });

    renderPrizeBreakdown(summary);
});

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
    populateScoresMemberFocus(memberNames);
    scoresHead.innerHTML = `<tr><th class="sticky-match-col">Match</th><th class="sticky-fixture-col">Fixture</th>${memberNames.map(name => `<th data-score-column="${escapeHtml(name)}">${escapeHtml(name)}</th>`).join('')}</tr>`;

    rows.forEach(match => {
        const scoreValues = memberNames
            .map(name => match.scores?.[name])
            .filter(value => value !== null && value !== undefined && value !== '');
        const maxScore = scoreValues.length ? Math.max(...scoreValues) : null;
        const row = document.createElement('tr');
        const cells = memberNames.map(name => {
            const value = match.scores?.[name];
            const isTop = maxScore !== null && value === maxScore;
            const baseClass = isTop ? 'score-cell is-top-score' : 'score-cell';
            return `<td class="${baseClass}" data-score-column="${escapeHtml(name)}">${formatCompactPoints(value)}</td>`;
        }).join('');
        row.innerHTML = `<td class="sticky-match-col">${formatText(match.matchNum)}</td><td class="sticky-fixture-col">${formatText(match.matchDetails)}</td>${cells}`;
        scoresBody.appendChild(row);
    });

    updateScoresTopScrollbar();
    setFocusedScoreColumn(scoresMemberFocus?.value || '');
}

function renderTableTracker(data) {
    (data.tableRankings || []).forEach(rowData => {
        const row = document.createElement('tr');
        const isPlayoffRank = Number(rowData.rank) <= 4;
        row.innerHTML = `<td class="${isPlayoffRank ? 'playoff-rank-cell' : ''}">${formatText(rowData.rank)}</td><td>${formatText(rowData.iplTeamName)}</td>`;
        tableRankingsBody.appendChild(row);

        if (Number(rowData.rank) === 4) {
            const cutoffRow = document.createElement('tr');
            cutoffRow.className = 'prediction-cutoff-row';
            cutoffRow.innerHTML = `
                <td class="prediction-cutoff-label">Playoff contention</td>
                <td class="prediction-cutoff-line" colspan="1"><span></span></td>
            `;
            tableRankingsBody.appendChild(cutoffRow);
        }
    });

    const memberNames = data.leagueMembers?.map(member => member.name) || [];
    predictionsHead.innerHTML = `<tr><th>Rank</th>${memberNames.map(name => `<th>${escapeHtml(name)}</th>`).join('')}</tr>`;

    (data.tablePredictions || []).forEach(prediction => {
        const row = document.createElement('tr');
        const cells = memberNames.map(name => `<td>${formatText(prediction.predictions?.[name])}</td>`).join('');
        const isPlayoffRank = Number(prediction.rank) <= 4;
        row.innerHTML = `<td class="${isPlayoffRank ? 'playoff-rank-cell' : ''}">${formatText(prediction.rank)}</td>${cells}`;
        predictionsBody.appendChild(row);

        if (Number(prediction.rank) === 4) {
            const cutoffRow = document.createElement('tr');
            cutoffRow.className = 'prediction-cutoff-row';
            cutoffRow.innerHTML = `
                <td class="prediction-cutoff-label">Playoff contention</td>
                <td class="prediction-cutoff-line" colspan="${memberNames.length}"><span></span></td>
            `;
            predictionsBody.appendChild(cutoffRow);
        }
    });

    const scoreCells = memberNames.map(name => `<td>${formatText(data.tablePredictionScores?.[name], '0')}</td>`).join('');
    const totalRow = document.createElement('tr');
    totalRow.className = 'prediction-total-row';
    totalRow.innerHTML = `<td>Total Points</td>${scoreCells}`;
    predictionsBody.appendChild(totalRow);
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
    const prizeSummaryLookup = buildPrizeSummaryLookup(data.participantPrizeSummary || []);
    currentPrizeSummaryLookup = prizeSummaryLookup;
    renderSyncStatus(data);
    renderLeaderboard(data, memberLookup, prizeSummaryLookup);
    renderMatchWinners(data, memberLookup);
    renderPlayerPrizes(data, memberLookup);
    renderBonusPrizes(data, memberLookup);
    renderMemberStats(data);
    renderMembers(data, memberLookup, prizeSummaryLookup);
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

if (scoresTableWrapper && scoresTopScrollbar) {
    scoresTableWrapper.addEventListener('scroll', () => syncScoresScroll(scoresTableWrapper, scoresTopScrollbar));
    scoresTopScrollbar.addEventListener('scroll', () => syncScoresScroll(scoresTopScrollbar, scoresTableWrapper));
    window.addEventListener('resize', updateScoresTopScrollbar);
}

if (scoresMemberFocus) {
    scoresMemberFocus.addEventListener('change', event => {
        setFocusedScoreColumn(event.target.value);
    });
}