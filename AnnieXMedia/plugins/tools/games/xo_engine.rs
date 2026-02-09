// file: AnnieXMedia/plugins/xo_engine.rs
// The Ultimate Rust Engine (Alpha-Beta Pruning)
// Dependency-free (uses internal LCG for randomness)

use std::cmp;
use std::ffi::CStr;
use std::os::raw::{c_char, c_int};
use std::time::{SystemTime, UNIX_EPOCH};

const AI: char = 'O';
const HUMAN: char = 'X';
const EMPTY: char = '-';

// --- Simple Random Number Generator (LCG) ---
// لأن Rust القياسية لا تحتوي على rand، نكتب واحد بسيط وسريع
static mut SEED: u64 = 0;

unsafe fn rand_init() {
    let start = SystemTime::now();
    let since_the_epoch = start.duration_since(UNIX_EPOCH).expect("Time went backwards");
    SEED = since_the_epoch.as_nanos() as u64;
}

unsafe fn rand_range(min: usize, max: usize) -> usize {
    if SEED == 0 { rand_init(); }
    SEED = SEED.wrapping_mul(6364136223846793005).wrapping_add(1);
    let r = (SEED >> 33) as usize;
    min + (r % (max - min))
}

// --- Game Logic ---

fn to_board(input_board: *const c_char) -> [char; 9] {
    let c_str = unsafe { CStr::from_ptr(input_board) };
    let str_slice = c_str.to_str().unwrap_or("---------");
    let mut board = [EMPTY; 9];
    for (i, c) in str_slice.chars().enumerate() {
        if i < 9 { board[i] = c; }
    }
    board
}

fn check_win_internal(b: &[char; 9]) -> char {
    let wins = [
        [0,1,2], [3,4,5], [6,7,8],
        [0,3,6], [1,4,7], [2,5,8],
        [0,4,8], [2,4,6]
    ];
    for w in wins.iter() {
        if b[w[0]] != EMPTY && b[w[0]] == b[w[1]] && b[w[1]] == b[w[2]] {
            return b[w[0]];
        }
    }
    if b.iter().all(|&c| c != EMPTY) { return 'D'; }
    'N'
}

// Alpha-Beta Pruning (Speed Optimization)
fn minimax(b: &mut [char; 9], depth: i32, is_max: bool, mut alpha: i32, mut beta: i32) -> i32 {
    let res = check_win_internal(b);
    if res == AI { return 100 - depth; }
    if res == HUMAN { return depth - 100; }
    if res == 'D' { return 0; }

    if is_max {
        let mut best = -10000;
        for i in 0..9 {
            if b[i] == EMPTY {
                b[i] = AI;
                let val = minimax(b, depth + 1, false, alpha, beta);
                b[i] = EMPTY;
                best = cmp::max(best, val);
                alpha = cmp::max(alpha, best);
                if beta <= alpha { break; }
            }
        }
        best
    } else {
        let mut best = 10000;
        for i in 0..9 {
            if b[i] == EMPTY {
                b[i] = HUMAN;
                let val = minimax(b, depth + 1, true, alpha, beta);
                b[i] = EMPTY;
                best = cmp::min(best, val);
                beta = cmp::min(beta, best);
                if beta <= alpha { break; }
            }
        }
        best
    }
}

// --- Exported Functions ---

#[no_mangle]
pub extern "C" fn check_winner_engine(input_board: *const c_char) -> c_char {
    let board = to_board(input_board);
    check_win_internal(&board) as c_char
}

#[no_mangle]
pub extern "C" fn get_hard_move(input_board: *const c_char) -> c_int {
    let mut board = to_board(input_board);
    
    // Smart Opening: Center
    if board[4] == EMPTY { return 4; }

    let mut best_val = -10000;
    let mut best_move = -1;

    for i in 0..9 {
        if board[i] == EMPTY {
            board[i] = AI;
            let move_val = minimax(&mut board, 0, false, -10000, 10000);
            board[i] = EMPTY;
            if move_val > best_val {
                best_move = i as i32;
                best_val = move_val;
            }
        }
    }
    best_move
}

#[no_mangle]
pub extern "C" fn get_medium_move(input_board: *const c_char) -> c_int {
    // 60% Hard, 40% Random
    unsafe {
        if rand_range(0, 10) < 6 {
            return get_hard_move(input_board);
        }
        let board = to_board(input_board);
        let mut moves = Vec::new();
        for i in 0..9 { if board[i] == EMPTY { moves.push(i); } }
        if moves.is_empty() { return -1; }
        return moves[rand_range(0, moves.len())] as c_int;
    }
}

#[no_mangle]
pub extern "C" fn get_easy_move(input_board: *const c_char) -> c_int {
    // Random
    unsafe {
        let board = to_board(input_board);
        let mut moves = Vec::new();
        for i in 0..9 { if board[i] == EMPTY { moves.push(i); } }
        if moves.is_empty() { return -1; }
        return moves[rand_range(0, moves.len())] as c_int;
    }
}
