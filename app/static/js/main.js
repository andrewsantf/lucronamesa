document.addEventListener(\'DOMContentLoaded\', function () {
    const costChartElement = document.getElementById(\'costChart\');
    if (costChartElement) {
        const ingredientNames = JSON.parse(costChartElement.dataset.names);
        const ingredientCosts = JSON.parse(costChartElement.dataset.costs);

        const ctx = costChartElement.getContext(\'2d\');
        new Chart(ctx, {
            type: \'pie\',
            data: {
                labels: ingredientNames,
                datasets: [{
                    data: ingredientCosts,
                    backgroundColor: [
                        \'rgba(255, 99, 132, 0.8)\',
                        \'rgba(54, 162, 235, 0.8)\',
                        \'rgba(255, 206, 86, 0.8)\',
                        \'rgba(75, 192, 192, 0.8)\',
                        \'rgba(153, 102, 255, 0.8)\',
                        \'rgba(255, 159, 64, 0.8)\'
                    ],
                    borderColor: [
                        \'rgba(255, 99, 132, 1)\',
                        \'rgba(54, 162, 235, 1)\',
                        \'rgba(255, 206, 86, 1)\',
                        \'rgba(75, 192, 192, 1)\',
                        \'rgba(153, 102, 255, 1)\',
                        \'rgba(255, 159, 64, 1)\'
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: \'top\',
                    },
                    title: {
                        display: true,
                        text: \'Distribuição de Custos por Ingrediente\'
                    }
                }
            }
        });
    }
});


