import sys,unittest,io,base64
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from misc_detector import detect_misc
from desktop_support import DesktopApi
FIXTURES=Path(__file__).resolve().parents[3]/'qa/misc-fixtures18'
class MiscDetectorTests(unittest.TestCase):
 def test_supplied_examples_and_locks(self):
  if not FIXTURES.exists():self.skipTest('User fixtures stored separately')
  expected={'1000368182.jpg':6,'1000368219.jpg':6,'1000368215.jpg':6,'1000368161.jpg':6,'1000368162.jpg':5,'1000368232.jpg':6,'1000368234.jpg':3}
  for name,count in expected.items():
   image=Image.open(FIXTURES/name).convert('RGB')
   for maxside in [1600,1200,900]:
    with self.subTest(name=name,size=maxside):
     f=min(1,maxside/max(image.size));im=image.resize((round(image.width*f),round(image.height*f)))
     result=detect_misc(im);self.assertTrue(result['detected']);self.assertEqual(len(result['rects']),count)
     if name=='1000368234.jpg':self.assertEqual(result['locked'],2)
     for x,y,x2,y2 in result['rects']:self.assertTrue(0<=x<x2<=im.width and 0<=y<y2<=im.height)
 def test_different_screen_aspect_and_translated_grid(self):
  if not FIXTURES.exists():self.skipTest('User fixtures stored separately')
  image=Image.open(FIXTURES/'1000368161.jpg').convert('RGB');tablet=Image.new('RGB',(2200,1650),(155,170,181));tablet.paste(image,(170,280))
  result=detect_misc(tablet);self.assertEqual(len(result['rects']),6);self.assertTrue(all(r[0]>1000 and r[1]>300 for r in result['rects']))
 def test_precropped_image_not_split(self):
  im=Image.new('RGB',(200,230),(130,20,50));ImageDraw.Draw(im).ellipse((50,30,150,200),fill='white')
  self.assertFalse(detect_misc(im)['detected'])
 def test_native_misc_without_ocr_engine(self):
  im=Image.new('RGB',(200,230),'red');output=io.BytesIO();im.save(output,'PNG')
  result=DesktopApi('test.log').read_misc(base64.b64encode(output.getvalue()).decode());self.assertFalse(result['detected'])
 def test_empty_tiles_are_not_returned(self):
  im=Image.new('RGB',(600,400),(180,180,180));draw=ImageDraw.Draw(im)
  for row in range(2):
   for col in range(3):draw.rectangle((50+col*130,50+row*130,169+col*130,169+row*130),fill=(40,40,40))
  result=detect_misc(im);self.assertTrue(result['detected']);self.assertEqual(result['rects'],[])

 def test_cut_top_row_skipped_and_next_six_selected(self):
  if not (FIXTURES/'balo-cut-top.jpg').exists():self.skipTest('User fixture stored separately')
  original=Image.open(FIXTURES/'balo-cut-top.jpg')
  for width in (1536,1200,900):
   with self.subTest(width=width):
    im=original.resize((width,round(original.height*width/original.width)));r=detect_misc(im)
    self.assertEqual(len(r['rects']),6)
    self.assertTrue(all(box[1]>280*width/1536 for box in r['rects']))
    self.assertTrue(all(box[3]<575*width/1536 for box in r['rects']))
 def test_single_supplied_tile_trimmed(self):
  if not (FIXTURES/'balo-single.jpg').exists():self.skipTest('User fixture stored separately')
  original=Image.open(FIXTURES/'balo-single.jpg')
  for width in (original.width,900):
   im=original.resize((width,round(original.height*width/original.width)));r=detect_misc(im)
   self.assertEqual(len(r['rects']),1);x,y,x2,y2=r['rects'][0]
   self.assertTrue(x>0 and y>0 and x2<im.width and y2<im.height)
 def test_one_row_two_and_three_tiles(self):
  for count in (2,3):
   with self.subTest(count=count):
    im=Image.new('RGB',(600,240),(180,180,180));draw=ImageDraw.Draw(im)
    for col in range(count):
     x=50+130*col;draw.rectangle((x,50,x+119,169),fill=(90,20,40));draw.ellipse((x+35,70,x+85,150),fill='white')
    r=detect_misc(im);self.assertEqual(len(r['rects']),count)

 def test_original_s31_single_tile_and_clipped_neighbors(self):
  path=FIXTURES/'balo-single-original.jpg'
  if not path.exists():self.skipTest('User fixture stored separately')
  original=Image.open(path)
  for width in (original.width,1200,900):
   with self.subTest(width=width):
    im=original.resize((width,round(original.height*width/original.width)));r=detect_misc(im)
    self.assertTrue(r['detected']);self.assertEqual(len(r['rects']),1)
    x,y,x2,y2=r['rects'][0];f=width/original.width
    self.assertTrue(200*f<x<240*f and 95*f<y<145*f)
    self.assertTrue(1220*f<x2<1280*f and 1280*f<y2<1340*f)
