// xo_engine.cpp
// Unbeatable AI with Alpha-Beta Pruning
// Compile: g++ -shared -o xo_engine.so -fPIC xo_engine.cpp

#include <iostream>
#include <vector>
#include <algorithm>
#include <limits>

extern "C" {

    const char AI = 'O';
    const char HUMAN = 'X';
    const char EMPTY = '-';

    char get_winner(const char* board) {
        int wins[8][3] = {
            {0,1,2}, {3,4,5}, {6,7,8},
            {0,3,6}, {1,4,7}, {2,5,8},
            {0,4,8}, {2,4,6}
        };
        for (int i=0; i<8; i++) {
            if (board[wins[i][0]] != EMPTY &&
                board[wins[i][0]] == board[wins[i][1]] &&
                board[wins[i][1]] == board[wins[i][2]])
                return board[wins[i][0]];
        }
        for(int i=0; i<9; i++) if(board[i]==EMPTY) return 'N';
        return 'D';
    }

    // Alpha-Beta Pruning: السرعة والذكاء
    int minimax(char* board, int depth, bool isMax, int alpha, int beta) {
        char result = get_winner(board);
        if (result == AI) return 100 - depth;
        if (result == HUMAN) return depth - 100;
        if (result == 'D') return 0;

        if (isMax) {
            int best = -10000;
            for (int i=0; i<9; i++) {
                if (board[i] == EMPTY) {
                    board[i] = AI;
                    int val = minimax(board, depth+1, false, alpha, beta);
                    board[i] = EMPTY;
                    best = std::max(best, val);
                    alpha = std::max(alpha, best);
                    if (beta <= alpha) break; // Pruning
                }
            }
            return best;
        } else {
            int best = 10000;
            for (int i=0; i<9; i++) {
                if (board[i] == EMPTY) {
                    board[i] = HUMAN;
                    int val = minimax(board, depth+1, true, alpha, beta);
                    board[i] = EMPTY;
                    best = std::min(best, val);
                    beta = std::min(beta, best);
                    if (beta <= alpha) break; // Pruning
                }
            }
            return best;
        }
    }

    int get_hard_move(const char* input_board) {
        char board[9];
        for(int i=0; i<9; i++) board[i] = input_board[i];

        // حركة استراتيجية: الوسط أو الأركان
        if(board[4] == EMPTY) return 4;

        int bestVal = -10000;
        int bestMove = -1;

        for (int i=0; i<9; i++) {
            if (board[i] == EMPTY) {
                board[i] = AI;
                int moveVal = minimax(board, 0, false, -10000, 10000);
                board[i] = EMPTY;
                if (moveVal > bestVal) {
                    bestMove = i;
                    bestVal = moveVal;
                }
            }
        }
        return bestMove;
    }

    int get_medium_move(const char* input_board) {
        if (rand() % 10 < 6) return get_hard_move(input_board);
        std::vector<int> moves;
        for(int i=0; i<9; i++) if(input_board[i] == EMPTY) moves.push_back(i);
        return moves.empty() ? -1 : moves[rand() % moves.size()];
    }

    int get_easy_move(const char* input_board) {
        std::vector<int> moves;
        for(int i=0; i<9; i++) if(input_board[i] == EMPTY) moves.push_back(i);
        return moves.empty() ? -1 : moves[rand() % moves.size()];
    }

    char check_winner_engine(const char* board) {
        return get_winner(board);
    }
}
