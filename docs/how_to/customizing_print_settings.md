# Customizing Print Settings

The `Print Setup` module in ProxyToolBox contains many settings that dictate how cards are rendered onto the output pages (PDF or PNG).

## Configuration Options

When creating your output sheets, you can modify the following parameters:

- **Card Width (`card_width_mm`)**: The width of the individual cards in millimeters. Standard MTG cards are 63mm.
- **Card Height (`card_height_mm`)**: The height of the individual cards in millimeters. Standard MTG cards are 88mm.
- **Corner Radius (`corner_radius_mm`)**: Controls the roundness of the card corners. 2.5mm is a good default.
- **Padding (`padding_mm`)**: The spacing between cards on the printed sheet to give you room to cut. Usually 2mm.
- **Output Format (`output_format`)**: Choose between `PDF` (for direct printing) and `PNG` (for dropping into other software).
- **Transformer Layout (`is_transformer`)**: A special flag for two-sided cards. If enabled, the system will look for appropriately named paired image files.

These settings are mapped directly to the `PrintSettings` Pydantic model (`src.models.PrintSettings`).

## Programmatic Modification

If you're using the frontend, these options are exposed via the settings modal.
If you're extending the backend logic directly, you can create a customized `PrintSettings` instance like so:

```python
from src.models import PrintSettings, OutputFormat

settings = PrintSettings(
    card_width_mm=62.5,  # Slightly tighter cut
    card_height_mm=87.5,
    padding_mm=1.0,
    corner_radius_mm=2.5,
    output_format=OutputFormat.PDF,
    is_transformer=False
)
```
