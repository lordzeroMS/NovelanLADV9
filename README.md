### Novelan LADV9 Heat Pump Integration

This Home Assistant integration allows you to monitor and control your Novelan LADV9 Heat Pump using Home Assistant. You can configure the IP address of your heat pump through the Home Assistant UI and control the heating stages (1-4).

#### Features
- Monitor the current state of the heat pump.
- Control the heat pump

### Installation Instructions

1. **Download the Integration:**
   Clone or download the repository and place the `novelan_ladv9` folder in your `custom_components` directory.

2. **Install Required Packages:**
   Ensure you have the required Python packages installed. You can install them using `pip`:
   ```sh
   pip install xmltodict homeassistant
   ```

3. **Configure the Integration:**
   - Go to the Home Assistant UI.
   - Navigate to `Configuration` > `Integrations`.
   - Click on the `+ Add Integration` button.
   - Search for `Novelan LADV9` and follow the prompts to configure the IP address of your heat pump.

### Usage Examples

#### Monitoring the Heat Pump

Once the integration is set up, you can monitor the heat pump's current state through the Home Assistant UI. The sensor will display the current heating rate.

#### Controlling the Heat Pump
TBD

### Tested Devices

This integration has been tested on the following devices:
- Novelan LADV9

### Integration with HACS

To integrate this custom component with HACS (Home Assistant Community Store):

1. **Add the Repository to HACS:**
   - Go to the HACS section in Home Assistant.
   - Click on the `+` button to add a new repository.
   - Select `Custom Repositories`.
   - Enter the URL of the repository and select the category as `Integration`.

2. **Install the Integration:**
   - After adding the repository, find the `Novelan LADV9` integration in the HACS store.
   - Click on `Install`.

3. **Configure the Integration:**
   - Follow the same configuration steps as mentioned above to set up the integration in Home Assistant.