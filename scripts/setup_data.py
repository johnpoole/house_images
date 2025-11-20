from core.models import Sheet, Camera

def run():
    # Create 8 sheets
    for i in range(1, 9):
        sheet, created = Sheet.objects.get_or_create(number=i)
        if created:
            print(f"Created Sheet {i}")
        
        # Create Odd camera
        # Assigning dummy device indices for now: 0, 1, 2...
        # In reality, user will need to update these via Admin
        idx_odd = (i - 1) * 2
        cam_odd, created = Camera.objects.get_or_create(sheet=sheet, side='odd', defaults={'device_index': idx_odd})
        if created:
            print(f"  Created Camera Odd (Index {idx_odd})")

        # Create Even camera
        idx_even = (i - 1) * 2 + 1
        cam_even, created = Camera.objects.get_or_create(sheet=sheet, side='even', defaults={'device_index': idx_even})
        if created:
            print(f"  Created Camera Even (Index {idx_even})")
