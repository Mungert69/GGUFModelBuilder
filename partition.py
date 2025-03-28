from datetime import datetime, timedelta

start_date = datetime(2022, 1, 1)
end_date = datetime(2024, 4, 1)  # Up to April 2024
current_date = start_date
partitions = []

while current_date < end_date:
    next_month = current_date.replace(day=28) + timedelta(days=4)  # This will never fail
    next_month_start = next_month - timedelta(days=next_month.day-1)
    seconds_since_start = int((next_month_start - start_date).total_seconds())
    partitions.append((current_date.strftime('%b%Y'), seconds_since_start))
    current_date = next_month_start

# Print SQL for partitions
for month, boundary in partitions:
    print(f"    PARTITION p{month} VALUES LESS THAN ({boundary}),")

# Catch-all partition
print("    PARTITION pMax VALUES LESS THAN MAXVALUE")

