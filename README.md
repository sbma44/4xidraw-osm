## Building a Docker image

The goal of this system is to enable rapid creation of SVGs from a given OSM extract without tediously reloading data.

### Using S3 (optional)

This system is designed to stick output SVGs onto S3. This is probably not useful for most 4xiDraw users and can be ignored.

If using S3, create `aws-config` in the same directory as the Dockerfile, populating it with appropriate credentials. I suggest using an IAM policy scoped to the particular output bucket. Here's an example:

```

```

You can build the image by passing in a link to a .osm.bz2 extract of an OSM region, like the ones supplied by geofabrik:

```
docker build -t 4xidraw-osm/new_york --build-arg DOWNLOAD=http://download.geofabrik.de/north-america/us/new-york-latest.osm.bz2 .
```

## Generating an SVG

With the Docker image built, you can run the task by passing in a [GeoJSON](https://geojson.io) bounding box for the area you're interested in and an output path. If using S3:

```
docker run 4xidraw-osm/new_york '{"type":"Polygon","coordinates":[[[-74.09,40.71],[-74.01,40.71],[-74.01,40.78],[-74.09,40.78],[-74.09,40.71]]]}' 's3://my-output-bucket'
```

If running locally:

```
docker run -v /path/to/my/output:/tmp/out 4xidraw-osm/new_york '{"type":"Polygon","coordinates":[[[-74.09,40.71],[-74.01,40.71],[-74.01,40.78],[-74.09,40.78],[-74.09,40.71]]]}' /tmp/out
```

## Using Inkscape

1. Copy `inkscape.*` to the [Inkscape extensions directory](https://inkscape.org/en/gallery/%3Dextension/). Restart Inkscape.
2. Open the SVG file.
3. Open `Document Properties` (ctrl + shift + d). Change `Units` to `px`. `Default Units` can be any value, but `mm` is recommended.
4. Select all paths (ctrl + alt + a) and scale them to the dimensions you want. The 4xiDraw's maximum print area is 280mm x 280mm.
5. Open the `Layers` dialog (shift + ctrl + l). Select a desired layer. Select all paths within the layer (ctrl + a).
6. Go to `Extensions > 4xiDraw > 4xiDraw Exporter...`
7. Specify a filename and output directory. Default should be fine. Hit OK.
8. You now have a mostl-printable gcode file! But do see the next section...

## Postprocessing

The generated gcode often has an inexplicable offset from the top left of the printable area, aka the origin. This can result in jobs that go out of bounds, damaging your machine. For this reason I have created `rationalize_gcode.py`, which processes one or more gcode files and translates all coordinates to use a minimum of 0, 0.

Why not integrate this logic into the exporter plugin? Simple: the plugin is designed to work with a single layer at a time. Translating layers independently would shift them out of alignment with one another.

You can use the script like so:

```
python3 /path/to/rationalize_gcode.py /path/to/gcode/*.g
```

This will create new versions of each file in your current directory, each with the new suffix `.translated.g`.

## Sending to 4xidraw

At the recommendation of the 4xiDraw docs, I've been using [Universal Gcode Sender](https://winder.github.io/ugs_website/) (UGS). I recommend version 1.0.9.

To use, open the application according to its instructions and connect to the 4xiDraw serial port at 115200 baud. Use the manual machine controls with a small step size (e.g. 10mm) and the `X-` and `Y-` buttons to job the pen holder to the point in its range furthest from the Arduino. At this point, hit the `Reset Zero` button. You have just defined the 0,0 origin point for your print.

Now you can use the UGS file sending mode to run a print using your generated gcode. Hit the `Return to Zero` button between each print.