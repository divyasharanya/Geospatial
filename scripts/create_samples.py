from pathlib import Path
import zipfile
import geopandas as gpd
from shapely.geometry import Polygon

root = Path(__file__).resolve().parents[1]
out = root / "samples"
work = out / "_shape_work"
work.mkdir(exist_ok=True)
frame = gpd.GeoDataFrame(
    {"name": ["1 km x 1 km square"]},
    geometry=[Polygon([(500000, 0), (501000, 0), (501000, 1000), (500000, 1000)])],
    crs="EPSG:32631",
)
shp = work / "square.shp"
frame.to_file(shp, engine="pyogrio")
archive = out / "square_shapefile.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
    for member in work.iterdir():
        if member.suffix.lower() in {".shp", ".shx", ".dbf", ".prj"}:
            target.write(member, f"nested/{member.name}")
for member in work.iterdir():
    member.unlink()
work.rmdir()
print(f"Created {archive}")
