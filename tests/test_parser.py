from src.order_processor import convert

def test_qty():
    assert convert(['2 pollo'])[0]['quantity']==2
