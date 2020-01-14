use pyo3::prelude::*;
use pyo3::types::*;
use raptorq::{
    Encoder as EncoderNative,
    Decoder as DecoderNative,
    SourceBlockEncoder as SourceBlockEncoderNative,
    SourceBlockDecoder as SourceBlockDecoderNative,
    ObjectTransmissionInformation,
    EncodingPacket,
};


#[pyclass]
struct SourceBlockEncoder {
    encoder: SourceBlockEncoderNative
}

#[pymethods]
impl SourceBlockEncoder {
    #[new]
    fn new(obj: &PyRawObject, source_block_id: u8, symbol_size: u16, data: &PyBytes) {
        let encoder = SourceBlockEncoderNative::new(source_block_id, symbol_size, data.as_bytes());
        obj.init({
            SourceBlockEncoder { encoder }
        });
    }

    pub fn source_packets<'p>(&self,
        py: Python<'p>,
    ) -> PyResult<Vec<&'p PyBytes>> {
        let packets: Vec<&PyBytes> = self.encoder.source_packets()
            .iter()
            .map(|packet| PyBytes::new(py, &packet.serialize()))
            .collect();

        Ok(packets)
    }

    pub fn repair_packets<'p>(&self, py: Python<'p>, start_repair_symbol_id: u32, packets: u32) -> PyResult<Vec<&'p PyBytes>> {
        let packets: Vec<&PyBytes> = self.encoder.repair_packets(start_repair_symbol_id, packets)
            .iter()
            .map(|packet| PyBytes::new(py, &packet.serialize()))
            .collect();

        Ok(packets)
    }
}

#[pyclass]
struct SourceBlockDecoder {
    decoder: SourceBlockDecoderNative
}

#[pymethods]
impl SourceBlockDecoder {
    #[new]
    fn new(obj: &PyRawObject, source_block_id: u8, symbol_size: u16, block_length: u64) {
        let decoder = SourceBlockDecoderNative::new(source_block_id, symbol_size, block_length);
        obj.init({
            SourceBlockDecoder { decoder }
        });
    }

    pub fn decode<'p>(&mut self, py: Python<'p>, packet: &PyBytes) -> PyResult<Option<&'p PyBytes>> {
        let result = self.decoder.decode(vec![EncodingPacket::deserialize(packet.as_bytes())]);
        Ok(result.map(|data| PyBytes::new(py, &data)))
    }
}

#[pyclass]
struct Encoder {
    encoder: EncoderNative
}

#[pymethods]
impl Encoder {
    #[staticmethod]
    pub fn with_defaults(data: &PyBytes, maximum_transmission_unit: u16) -> PyResult<Encoder> {
        let encoder = EncoderNative::with_defaults(data.as_bytes(), maximum_transmission_unit);
        Ok(Encoder { encoder })
    }

    pub fn get_encoded_packets<'p>(&self,
        py: Python<'p>,
        repair_packets_per_block: u32,
    ) -> PyResult<Vec<&'p PyBytes>> {
        let packets: Vec<&PyBytes> = self.encoder.get_encoded_packets(repair_packets_per_block)
            .iter()
            .map(|packet| PyBytes::new(py, &packet.serialize()))
            .collect();

        Ok(packets)
    }
}

#[pyclass]
struct Decoder {
    decoder: DecoderNative
}

#[pymethods]
impl Decoder {
    #[staticmethod]
    pub fn with_defaults(transfer_length: u64, maximum_transmission_unit: u16) -> PyResult<Decoder> {
        let config = ObjectTransmissionInformation::with_defaults(
            transfer_length,
            maximum_transmission_unit,
        );
        let decoder = DecoderNative::new(config);
        Ok(Decoder { decoder })
    }

    pub fn decode<'p>(&mut self, py: Python<'p>, packet: &PyBytes) -> PyResult<Option<&'p PyBytes>> {
        let result = self.decoder.decode(EncodingPacket::deserialize(packet.as_bytes()));
        Ok(result.map(|data| PyBytes::new(py, &data)))
    }
}

#[pymodule]
fn raptorq(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<SourceBlockEncoder>()?;
    m.add_class::<SourceBlockDecoder>()?;
    m.add_class::<Encoder>()?;
    m.add_class::<Decoder>()?;
    Ok(())
}