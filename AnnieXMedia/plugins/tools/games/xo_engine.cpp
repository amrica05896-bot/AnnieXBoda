// xo_engine.cpp
// هذا الكود هو "العقل" المدبر للعبة
#include <iostream>
#include <vector>
#include <algorithm>
#include <cstdlib>
#include <ctime>

extern "C" {

    const char PLAYER_X = 'X';
    const char PLAYER_O = 'O';
    const char EMPTY = '-';

    // 1. فحص الفائز (سريع جداً)
    char check_winner_engine(const char* board) {
        int wins[8][3] = {
            {0, 1, 2}, {3, 4, 5}, {6, 7, 8}, // أفقي
            {0, 3, 6}, {1, 4, 7}, {2, 5, 8}, // رأسي
            {0, 4, 8}, {2, 4, 6}             // قطري
        };

        for (int i = 0; i < 8; i++) {
            if (board[wins[i][0]] != EMPTY &&
                board[wins[i][0]] == board[wins[i][1]] &&
                board[wins[i][1]] == board[wins[i][2]]) {
                return board[wins[i][0]];
            }
        }

        for (int i = 0; i < 9; i++) {
            if (board[i] == EMPTY) return 'N'; // اللعب مستمر
        }
        return 'D'; // تعادل
    }

    // دالة مساعدة للميني ماكس
    int minimax(char* board, int depth, bool isMaximizing) {
        char result = check_winner_engine(board);
        if (result == PLAYER_O) return 10 - depth;
        if (result == PLAYER_X) return depth - 10;
        if (result == 'D') return 0;

        if (isMaximizing) {
            int bestScore = -1000;
            for (int i = 0; i < 9; i++) {
                if (board[i] == EMPTY) {
                    board[i] = PLAYER_O;
                    int score = minimax(board, depth + 1, false);
                    board[i] = EMPTY;
                    bestScore = std::max(score, bestScore);
                }
            }
            return bestScore;
        } else {
            int bestScore = 1000;
            for (int i = 0; i < 9; i++) {
                if (board[i] == EMPTY) {
                    board[i] = PLAYER_X;
                    int score = minimax(board, depth + 1, true);
                    board[i] = EMPTY;
                    bestScore = std::min(score, bestScore);
                }
            }
            return bestScore;
        }
    }

    // 2. حركة البوت (الوضع الصعب - مستحيل الفوز عليه)
    int get_hard_move(const char* input_board) {
        char board[9];
        for(int i=0; i<9; i++) board[i] = input_board[i];

        int bestScore = -1000;
        int move = -1;

        for (int i = 0; i < 9; i++) {
            if (board[i] == EMPTY) {
                board[i] = PLAYER_O;
                int score = minimax(board, 0, false);
                board[i] = EMPTY;
                if (score > bestScore) {
                    bestScore = score;
                    move = i;
                }
            }
        }
        return move;
    }

    // 3. حركة البوت (الوضع المتوسط - 50% ذكاء)
    int get_medium_move(const char* input_board) {
        srand(time(0));
        if (rand() % 2 == 0) return get_hard_move(input_board);
        
        std::vector<int> empty_spots;
        for(int i=0; i<9; i++) if(input_board[i] == EMPTY) empty_spots.push_back(i);
        if (empty_spots.empty()) return -1;
        return empty_spots[rand() % empty_spots.size()];
    }

    // 4. حركة البوت (الوضع السهل - عشوائي)
    int get_easy_move(const char* input_board) {
        srand(time(0));
        std::vector<int> empty_spots;
        for(int i=0; i<9; i++) if(input_board[i] == EMPTY) empty_spots.push_back(i);
        if (empty_spots.empty()) return -1;
        return empty_spots[rand() % empty_spots.size()];
    }
}
