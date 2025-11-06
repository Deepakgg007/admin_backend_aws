
'use strict';

function compareTriplets(a, b) {
    // Write your code here
    return [];
}

function main() {
    const readline = require('readline');

    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
        terminal: false
    });

    let inputLines = [];

    rl.on('line', function (line) {
        inputLines.push(line);
        if (inputLines.length === 2) {
            const a = inputLines[0].split(' ').map(Number);
            const b = inputLines[1].split(' ').map(Number);
            const result = compareTriplets(a, b);
            console.log(result.join(' '));
            rl.close();
        }
    });
}

main();
