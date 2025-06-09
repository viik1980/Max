
from datetime import datetime, timedelta

def calculate_eta(start_time, segments, speed_kmh=73):
    events = []
    current_time = start_time
    total_distance = 0

    for segment in segments:
        if segment["type"] == "drive":
            duration = timedelta(hours=segment["distance_km"] / speed_kmh)
            end_time = current_time + duration
            events.append({
                "start": current_time,
                "end": end_time,
                "action": f"Вождение {segment['distance_km']} км"
            })
            current_time = end_time
            total_distance += segment["distance_km"]
        elif segment["type"] == "wait":
            duration = timedelta(minutes=segment["duration_min"])
            end_time = current_time + duration
            events.append({
                "start": current_time,
                "end": end_time,
                "action": segment.get("note", "Ожидание")
            })
            current_time = end_time
        elif segment["type"] == "pause":
            duration = timedelta(minutes=segment["duration_min"])
            end_time = current_time + duration
            events.append({
                "start": current_time,
                "end": end_time,
                "action": segment.get("note", "Пауза")
            })
            current_time = end_time

    return events, total_distance
