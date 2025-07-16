// Simplified US states geometry for self-contained map
// This is a simplified version - for production, use full resolution data
export const US_STATES_GEOJSON = {
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "name": "United States" },
      "geometry": {
        "type": "MultiPolygon",
        "coordinates": [
          // Continental US simplified outline
          [[
            [-125, 49], [-125, 48], [-124, 46], [-124, 40], [-124, 35],
            [-120, 34], [-117, 32.5], [-114.5, 32.5], [-111, 31], 
            [-108, 31], [-108, 32], [-106, 32], [-104, 33], [-103, 36],
            [-102, 37], [-100, 36], [-98, 35], [-96, 35], [-94, 33],
            [-94, 30], [-93, 29], [-91, 29], [-89, 29], [-84, 30],
            [-82, 28], [-81, 25], [-80, 25], [-80, 31], [-75, 35],
            [-75, 40], [-71, 41], [-70, 42], [-69, 45], [-67, 45],
            [-67, 47], [-69, 47], [-70, 46], [-74, 45], [-75, 45],
            [-79, 43], [-83, 42], [-83, 46], [-87, 45], [-90, 46],
            [-92, 46], [-94, 49], [-95, 49], [-123, 49], [-125, 49]
          ]],
          // Alaska simplified
          [[
            [-168, 71], [-168, 65], [-164, 63], [-161, 63], [-161, 66],
            [-163, 69], [-166, 70], [-168, 71]
          ]],
          // Hawaii simplified
          [[
            [-160, 22], [-160, 21], [-159, 21], [-157, 21], [-156, 20],
            [-155, 19], [-155, 20], [-156, 21], [-158, 22], [-160, 22]
          ]]
        ]
      }
    }
  ]
};

// State boundaries would go here - for now just showing approach
export const STATE_BOUNDARIES = {
  "type": "FeatureCollection",
  "features": [
    // Each state would have its boundary here
    // This is where you'd include actual state boundaries from Census data
  ]
};