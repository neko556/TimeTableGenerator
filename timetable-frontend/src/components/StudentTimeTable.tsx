// timetable-frontend/src/components/StudentTimeTable.tsx
import React from "react";

type TimetableEntry = {
  "Batch/Group ID"?: string;
  "Course ID"?: string;
  "Day": string;
  "Faculty ID"?: string;
  "Room ID"?: string;
  "Time"?: string;
  "Time Slot"?: string;
};

// fixed weekday order (always show these rows)
const DAY_ORDER = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

// convert "HH:MM-..." to minutes (for sorting)
function toMinutes(slot: string) {
  if (!slot) return 0;
  // accept both hyphen "-" and en-dash "–"
  const sep = slot.includes("-") ? "-" : slot.includes("–") ? "–" : "-";
  const start = slot.split(sep)[0].trim();
  const match = start.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return 0;
  const [, hh, mm] = match;
  return parseInt(hh, 10) * 60 + parseInt(mm, 10);
}

// sanitize "Monday_10:00-11:00" -> "10:00-11:00"
function sanitizeSlot(raw: string | undefined) {
  if (!raw) return "";
  // if it contains an underscore and starts with a weekday, drop the prefix
  const parts = raw.split("_");
  if (parts.length >= 2 && DAY_ORDER.includes(parts[0])) {
    return parts.slice(1).join("_");
  }
  return raw;
}

export default function StudentTimetable({
  studentId,
  timetable,
}: {
  studentId: string;
  timetable: TimetableEntry[];
}) {
  if (!timetable || timetable.length === 0) {
    return (
      <p className="text-gray-600">No classes found for student {studentId}.</p>
    );
  }

  // === Build unique, sorted timeSlots (top row) ===
  const timeSlotsSet = new Set<string>();
  timetable.forEach((t) => {
    const s = sanitizeSlot(t["Time Slot"] ?? t["Time"]);
    if (s) timeSlotsSet.add(s);
  });

  const timeSlots = Array.from(timeSlotsSet).sort((a, b) =>
    toMinutes(a) - toMinutes(b)
  );

  if (timeSlots.length === 0) {
    return (
      <p className="text-gray-600">
        No time slots available in the timetable data for {studentId}.
      </p>
    );
  }

  // === Build grid: timeSlot -> day -> entry ===
  const grid: Record<string, Record<string, TimetableEntry | null>> = {};
  timeSlots.forEach((slot) => {
    grid[slot] = {};
    DAY_ORDER.forEach((d) => {
      grid[slot][d] = null;
    });
  });

  timetable.forEach((entry) => {
    const slot = sanitizeSlot(entry["Time Slot"] ?? entry["Time"]);
    if (!slot) return;
    const day = entry.Day;
    if (!DAY_ORDER.includes(day)) return; // ignore unknown day names
    // if multiple entries map to same (slot,day) we'll keep the last one — adjust if you want merging
    grid[slot][day] = entry;
  });

  // === Render ===
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">📅 Timetable for {studentId}</h2>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse border text-sm text-center">
          <thead className="bg-gray-100">
            <tr>
              <th className="border px-3 py-2">Day</th>
              {timeSlots.map((slot) => (
                <th key={slot} className="border px-3 py-2 whitespace-nowrap">
                  {slot}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {DAY_ORDER.map((day) => (
              <tr key={day}>
                <td className="border px-3 py-2 font-semibold bg-gray-50">
                  {day}
                </td>

                {timeSlots.map((slot) => {
                  const entry = grid[slot][day];
                  return (
                    <td
                      key={day + "|" + slot}
                      className="border px-3 py-2 align-top hover:bg-gray-50"
                    >
                      {entry ? (
                        <div className="space-y-1">
                          <div className="font-medium">{entry["Course ID"]}</div>
                          <div className="text-xs text-gray-600">
                            {entry["Faculty ID"]}
                          </div>
                          <div className="text-xs text-gray-500">
                            {entry["Room ID"]}
                          </div>
                        </div>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
