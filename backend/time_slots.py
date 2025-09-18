from datetime import datetime, timedelta

def generate_time_slots():
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    start_hour = 10
    end_hour = 17
    slot_duration = 60  # minutes
    
    slots = []
    slot_mapping = {}
    next_slot_map = {}  # This map will link a slot to the one immediately after it
    slot_id = 1
    
    for day in days:
        current_time = datetime.strptime(f"{start_hour}:00", "%H:%M")
        end_time = datetime.strptime(f"{end_hour}:00", "%H:%M")
        
        day_slots = [] # Temporarily store slots for a single day
        while current_time < end_time:
            if current_time.hour == 12:
                current_time += timedelta(minutes=slot_duration)
                continue
            slot_label = f"{day}_{current_time.strftime('%H:%M')}-{(current_time + timedelta(minutes=slot_duration)).strftime('%H:%M')}"
            slots.append(slot_label)
            slot_mapping[slot_label] = slot_id
            day_slots.append(slot_label) # Add to the day's list
            
            slot_id += 1
            current_time += timedelta(minutes=slot_duration)
        
        # After generating all slots for a day, create the sequence map
        for i in range(len(day_slots) - 1):
            next_slot_map[day_slots[i]] = day_slots[i+1]
            
    return slots, slot_mapping, next_slot_map # Return all three items