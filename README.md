# CineBook - Cinema Reservation System with Waitlist
Flask (Python) + SQLite backend, React (Vite) frontend.

## Requirements
- Python 3.9+  (check: `python --version`)
- Node.js 18+  (check: `node --version`)

## Run (two terminals)

### Terminal 1 - Backend (http://127.0.0.1:5000)
    cd backend
    python -m venv venv
    # Windows:      venv\Scripts\activate
    # Mac / Linux:  source venv/bin/activate
    pip install -r requirements.txt
    python app.py

The SQLite file `backend/cinema.db` is created automatically with sample data on first run.
(Delete that file to reset everything.)

### Terminal 2 - Frontend (http://localhost:5173)
    cd frontend
    npm install
    npm run dev

Open http://localhost:5173

## Demo accounts
| Role  | Email             | Password |
|-------|-------------------|----------|
| Admin | admin@cinema.com  | admin123 |
| User  | user@cinema.com   | user123  |
| User  | user2@cinema.com  | user123  |

## Try the waitlist (2 minutes)
1. Login as **user@cinema.com** -> Inception -> show on "Screen 4 (Mini - waitlist demo)". It is fully booked (by Riya).
2. Choose seats wanted (e.g. 3) -> **Join waitlist** (you see your queue position).
3. Open a second browser/incognito window, login as **user2@cinema.com** -> My Bookings -> cancel the Screen 4 booking.
4. Back as user1: Notifications shows "seats allotted from waitlist", and My Bookings has the new booking (marked "via waitlist").

## Features
User: register/login, search movies, view shows, live seat map (auto-refresh), book up to 6 seats, booking confirmation,
view/cancel bookings, join/leave waitlist with queue position, notifications.
Admin: dashboard (bookings, revenue, cancellations, waitlist size, occupancy per show, top movies), add/edit/delete movies,
add/delete shows (custom rows x columns), block/unblock seats, search all bookings (ID / name / email), cancel bookings.

## Data structures & algorithms (backend/app.py)
- 2D matrix `SeatMatrix` per show - O(1) seat check/update; scans rows for N adjacent free seats (best-seat suggestion for waitlist allotment)
- HashMaps `BOOKING_INDEX` (bookingId -> record) and `USER_INDEX` (userId -> bookings) - O(1) lookup
- FIFO queue (`deque`) per show - waitlist; on cancellation the queue is walked from the front and every request that fits is auto-booked
- Sorted order by time for shows (TreeMap-style), `heapq.nlargest` (max-heap) for top movies
- Per-show `threading.Lock` + atomic `UPDATE ... WHERE status='AVAILABLE'` + `UNIQUE(show_id, seat_row, seat_col)` -> a seat can never be given to two people

## Database tables (SQLite)
users, movies, shows, seats, bookings, booking_seats, waitlist, notifications

## Troubleshooting
- "Request failed (is the backend running?)" -> start the backend first (Terminal 1).
- Port 5000 busy (macOS AirPlay) -> change the port in `backend/app.py` (last line) and in `frontend/vite.config.js` proxy.
