import unittest
from unittest.mock import AsyncMock, Mock, patch
from app.config import Settings
from app.services.external_data import ExternalDataService


def response(data=None,text=''):
    result=Mock();result.json.return_value=data;result.text=text;return result


class BitcoinDataTests(unittest.IsolatedAsyncioTestCase):
    async def run_poll(self,name,responses):
        service=ExternalDataService(Settings(_env_file=None,dht_enabled=False))
        service._running=True;service.cache['btc_block_height']=960000
        client=AsyncMock();client.get=AsyncMock(side_effect=responses)
        client.__aenter__.return_value=client
        async def finish(_):service._running=False
        with patch('app.services.external_data.httpx.AsyncClient',return_value=client),patch('app.services.external_data.asyncio.sleep',side_effect=finish):
            await getattr(service,name)()
        return service,client

    async def test_price_change_requests_real_24h_value_and_rejects_nan(self):
        service,client=await self.run_poll('_poll_btc',[response({'bitcoin':{'eur':50000,'eur_24h_change':-2.3}})])
        self.assertEqual(service.cache['btc_eur'],50000);self.assertEqual(service.cache['btc_change_24h'],-2.3)
        self.assertEqual(client.get.call_args.kwargs['params']['include_24hr_change'],'true')
        service,_=await self.run_poll('_poll_btc',[response({'bitcoin':{'eur':float('nan')}})])
        self.assertIsNone(service.cache['btc_eur']);self.assertIsNotNone(service.cache['btc_error'])

    async def test_network_height_binding_and_fee_validation(self):
        fees={key:3 for key in ('economyFee','hourFee','halfHourFee','fastestFee')}
        service,_=await self.run_poll('_poll_btc_network',[response(fees),response(text='a'*64),response({'height':960000,'timestamp':1700000000})])
        self.assertEqual(service.cache['btc_fees'],fees);self.assertEqual(service.cache['btc_block_details_height'],960000)
        self.assertEqual(service.cache['btc_block_time'],1700000000)
        service,_=await self.run_poll('_poll_btc_network',[response(fees),response(text='a'*64),response({'height':960001,'timestamp':1700000000})])
        self.assertIsNotNone(service.cache['btc_block_details_error']);self.assertNotIn('btc_block_time',service.cache)

    async def test_fee_failure_does_not_prevent_block_metadata(self):
        service,_=await self.run_poll('_poll_btc_network',[RuntimeError('offline'),response(text='b'*64),response({'height':960000,'timestamp':1700000000})])
        self.assertEqual(service.cache['btc_fees_error'],'offline');self.assertEqual(service.cache['btc_block_time'],1700000000)

    async def test_invalid_height_is_not_published(self):
        for text in ('-1','nan','100000001'):
            service,_=await self.run_poll('_poll_btc_block_height',[response(text=text)])
            self.assertEqual(service.cache['btc_block_height'],960000)
            self.assertIsNotNone(service.cache['btc_block_height_error'])
