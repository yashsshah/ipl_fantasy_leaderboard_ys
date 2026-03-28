// Fetch data and populate leaderboard & prizes
fetch('data.json')
    .then(response => response.json())
    .then(data => {
        const leaderboardBody = document.getElementById('leaderboard-body');
        data.players.forEach((player, index) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${index + 1}</td>
                <td>${player.name}</td>
                <td>${player.totalPoints}</td>
                <td>${player.prizes.join(', ') || '-'}</td>
            `;
            leaderboardBody.appendChild(row);
        });

        const matchList = document.getElementById('match-list');
        data.matches.forEach(match => {
            const li = document.createElement('li');
            li.textContent = `Match ${match.match}: ${match.winner} (${match.points} pts)`;
            matchList.appendChild(li);
        });

        const prizeList = document.getElementById('player-prizes-list');
        data.playerPrizes.forEach(prize => {
            const li = document.createElement('li');
            li.textContent = `${prize.prize} – ${prize.player} ($${prize.amount})`;
            prizeList.appendChild(li);
        });
    })
    .catch(err => console.error('Error loading data:', err));