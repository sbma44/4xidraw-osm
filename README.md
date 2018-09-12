![demo](etc/demo.gif)

# 4xidraw-OSM

Have your robot draw parts of OpenStreetMap (OSM).

The goal of this system is to enable rapid creation of SVGs from a given OSM extract without tediously reloading data, then to convert the SVG data to Gcode that the 4xiDraw can use. The project employs Docker to make dependency installation less painful. The [4xiDraw is an open design](https://www.instructables.com/id/4xiDraw/) that lets anyone build their own pen plotter robot.

There are a few parts:

- a Docker-based set of scripts for creating SVGs from OSM extracts
- an improved version of the 4xiDraw Inkscape plugin for converting SVGs to gcode
- a post-processing script to rationalize separate gcode files from multilayer SVGs

Note that the last two components are likely to be combined after a pending refactor.

## Building the base image (optional)

You probably don't have to do this -- you should be able to pull the prebuilt image from Docker Hub. But for the record:

```
docker build -t sbma44/4xidraw-osm:base -f Dockerfile.base .
```

## Building an extract image

OSM is quite large, and you might only be interested in a small area. For this reason the system is designed to load data for a particular OSM extract.

When building, you must specify which OSM extract(s) your image will store. You can do so by passing in comma-separated links to one or more .osm.bz2 extract(s) of an OSM region, like the ones supplied by [Geofabrik](https://www.geofabrik.de/data/download.html):

```
docker build -t sbma44/4xidraw-osm:new-york --build-arg DOWNLOAD=http://download.geofabrik.de/north-america/us/new-york-latest.osm.bz2 .
```

## Generating an SVG

With the Docker image built, you can run the task by passing in a [GeoJSON](https://geojson.io) bounding box for the area you're interested in and an output path.

### Storing output locally

Local output is enabled by using Docker's `-v` flag to map a local folder to the Docker container's filesystem, like so:

```
docker run -v /path/to/my/output:/tmp/out sbma44/4xidraw-osm:new-york '{"type":"Polygon","coordinates":[[[-74.09,40.71],[-74.01,40.71],[-74.01,40.78],[-74.09,40.78],[-74.09,40.71]]]}' /tmp/out
```

Note that in the above example, `/tmp/out` is the path used within the container. In general, you should not change this value. `/path/to/my/output` is the local path where you can retrieve your SVG after the process has completed.

### Storing output on S3

If you pass in AWS credentials as environment variables and specify an S3 path as the output location, the result will be compressed and placed on S3:

```
docker run -e AWS_ACCESS_KEY_ID=ABCDEFGHIJKLM -e AWS_SECRET_ACCESS_KEY=1234567890 sbma44/4xidraw-osm:new-york '{"type":"Polygon","coordinates":[[[-74.09,40.71],[-74.01,40.71],[-74.01,40.78],[-74.09,40.78],[-74.09,40.71]]]}' 's3://my-output-bucket'
```

### Overriding layer selection (advanced)

By default, your output SVG will contain layers for streets, buildings, alleys, train tracks and bicycle paths. This is not a particularly cartographically well-tuned selection; I recommend tweaking it. It's possible to specify your own selection criteria by passing the container an environment variable named `LAYERS` in the format: `LAYER_NAME|TABLE_NAME|WHERE_CLAUSE`. Here's an example. Assume the following is stored in a file called `layers.txt`.

```
highway|planet_osm_line|highway IS NOT NULL
bicycle|planet_osm_line|route='bicycle'
train|planet_osm_line|route='train'
building|planet_osm_polygon|building IS NOT NULL
```

You could then invoke it with:

```
docker run -e LAYERS="$(cat layers.txt)" -v /tmp/4xidraw:/tmp/out sbma44/4xidraw-osm:district-of-columbia '{"type":"Polygon","coordinates":[[[-77,38.87],[-76.97,38.87],[-76.97,38.9],[-77,38.9],[-77,38.87]]]}' /tmp/out
```

This feature assumes familiarity with the default table schema created by the [osm2pgsql](https://wiki.openstreetmap.org/wiki/Osm2pgsql) tool. I suggest running the container with a bash prompt override of `--entrypoint` and the `-P` flag to open up the exposed port 5432. Start the postgresql service, connect to the relevant port with QGIS, and inspect the data to assemble the filter criteria you want.

## Using Inkscape

The Docker container will create SVGs intended for further editing in Inkscape.

### Setup

- Copy `inkscape/4xidraw.*` to the [Inkscape extensions directory](https://inkscape.org/en/gallery/%3Dextension/).
- If you plan to draw solid, filled-in shapes, I strongly recommend installing the [AxiDraw software](http://wiki.evilmadscientist.com/Axidraw_Software_Installation) for its Hatching extension.
- Restart Inkscape.

### Converting an SVG to Gcode

1. Open the SVG file.
2. Open `Document Properties` (ctrl + shift + d). Change `Units` to `px`. If the setting is already `px` you may need to switch it to something else, then back to `px` -- this is an Inkscape bug. `Default Units` can be any value, but `mm` is recommended.
3. If your project will involve multiple layers (e.g. the use of different writing instruments), separate the SVG into different layers. Output from the Docker script will already be in this format.
4. Edit shapes as necessary.
5. Select all geometry in all layers with (ctrl + alt + a). Note that layers must be visible and unlocked to be selected.
6. Go to `Extensions > 4xiDraw > 4xiDraw Exporter...`
7. Specify an output directory. Gcode files will be placed there, named after each layer's `id` value. Docker-generated layers will be named appropriately, but if you create new layers you may wish to edit the ID manually in the Inkscape XML editor to avoid a name like `layer18.gcode`.
8. Decide what options to use:
  - You can scale geometry by a constant factor (not recommended)
  - You can specify a bounding width along the X and/or Y axis, to which all layers will be scaled
  - You can collapse paths together, minimizing pen lifts for very small moves. This helps join together OSM geometry into continuous paths -- ths is good for both speed and line quality. However it will negatively affect layers with very precise geometry or small features like hatching (or buildings, potentially). Use with caution.
  - The `Advanced` features are inherited and I can't speak intelligently about them. In my own use I have sometimes lowered the tolerance values to get more precise arcs. I don't see a ton of difference, to be honest.

## What comes out

Each layer is generated and then reconciled against one another. Each is translated to that the collective drawing has an origin of (0,0). Consider this when setting the margin for your drawing!

## Sending to 4xiDraw

At the recommendation of the 4xiDraw docs, I've been using [Universal Gcode Sender](https://winder.github.io/ugs_website/) (UGS). I recommend version 1.0.9 or higher.

To use, open the application according to its instructions and connect to the 4xiDraw serial port at 115200 baud. Use the manual machine controls with a small step size (e.g. 10mm) and the `X-` and `Y-` buttons to jog the pen holder to the point in its range furthest from the Arduino. At this point, hit the `Reset Zero` button. You have just defined the 0,0 origin point for your print.

Now you can use the UGS file sending mode to run a print using your generated gcode. Hit the `Return to Zero` button between each print.

I strongly recommend using the `Visualize` option to determine if there are any unexpected offsets or invisible paths in your gcode. Failure to do so can damage your machine.

## License

It's important to note that OpenStreetMap data is licensed under the [Open Database License (ODbL)](https://www.openstreetmap.org/copyright). The ODbL carries attribution requirements that are likely to apply to works produced with this software, including drawings made by a 4xiDraw. Redistribution of OSM data, including via built Docker images, also carries obligations under the ODbL. It is your responsibility to understand and comply with these requirements; please be sure to familiarize yourself with them.

The Inkscape plugin descends from a long lineage of badly-written GPLv2 Python, so that is the primary license for this repo. I have offered my original contributions under a dual licensing scheme as well (BSD). Please see [LICENSE.md](LICENSE.md) for more details. Please take careful note of the disclaimers present in that file, as sending your 4xiDraw bad gcode can damage the machine and objects in its vicinity.

This code was written for my own use, for which it has proven satisfactory. But I cannot and will not accept responsibility for its use or any damage or injury that might result. Please do not use this code if you are unwilling to assume this risk.
