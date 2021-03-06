# -*- coding: utf-8 -*-
import unittest
import string
from zlib import decompress
from random import choice

from minecraft import SUPPORTED_PROTOCOL_VERSIONS
from minecraft.networking.connection import ConnectionContext
from minecraft.networking.types import (
    VarInt, Enum, Vector, PositionAndLook
)
from minecraft.networking.packets import (
    Packet, PacketBuffer, PacketListener, KeepAlivePacket, serverbound,
    clientbound
)


class PacketBufferTest(unittest.TestCase):
    def test_basic_read_write(self):
        message = b"hello"

        packet_buffer = PacketBuffer()
        packet_buffer.send(message)

        packet_buffer.reset_cursor()
        self.assertEqual(packet_buffer.read(), message)
        packet_buffer.reset_cursor()
        self.assertEqual(packet_buffer.recv(), message)

        packet_buffer.reset()
        self.assertNotEqual(packet_buffer.read(), message)

    def test_get_writable(self):
        message = b"hello"

        packet_buffer = PacketBuffer()
        packet_buffer.send(message)

        self.assertEqual(packet_buffer.get_writable(), message)


class PacketSerializationTest(unittest.TestCase):

    def test_packet(self):
        for protocol_version in SUPPORTED_PROTOCOL_VERSIONS:
            context = ConnectionContext(protocol_version=protocol_version)

            packet = serverbound.play.ChatPacket(context)
            packet.message = u"κόσμε"

            packet_buffer = PacketBuffer()
            packet.write(packet_buffer)

            packet_buffer.reset_cursor()
            # Read the length and packet id
            VarInt.read(packet_buffer)
            packet_id = VarInt.read(packet_buffer)
            self.assertEqual(packet_id, packet.id)

            deserialized = serverbound.play.ChatPacket(context)
            deserialized.read(packet_buffer)

            self.assertEqual(packet.message, deserialized.message)

    def test_compressed_packet(self):
        for protocol_version in SUPPORTED_PROTOCOL_VERSIONS:
            context = ConnectionContext(protocol_version=protocol_version)

            msg = ''.join(choice(string.ascii_lowercase) for i in range(500))
            packet = serverbound.play.ChatPacket(context)
            packet.message = msg

            self.write_read_packet(packet, 20)
            self.write_read_packet(packet, -1)

    def write_read_packet(self, packet, compression_threshold):
        for protocol_version in SUPPORTED_PROTOCOL_VERSIONS:
            context = ConnectionContext(protocol_version=protocol_version)

            packet_buffer = PacketBuffer()
            packet.write(packet_buffer, compression_threshold)

            packet_buffer.reset_cursor()

            VarInt.read(packet_buffer)
            compressed_size = VarInt.read(packet_buffer)

            if compressed_size > 0:
                decompressed = decompress(packet_buffer.read(compressed_size))
                packet_buffer.reset()
                packet_buffer.send(decompressed)
                packet_buffer.reset_cursor()

            packet_id = VarInt.read(packet_buffer)
            self.assertEqual(packet_id, packet.id)

            deserialized = serverbound.play.ChatPacket(context)
            deserialized.read(packet_buffer)

            self.assertEqual(packet.message, deserialized.message)


class PacketListenerTest(unittest.TestCase):

    def test_listener(self):
        message = "hello world"

        def test_packet(chat_packet):
            self.assertEqual(chat_packet.message, message)

        for protocol_version in SUPPORTED_PROTOCOL_VERSIONS:
            context = ConnectionContext(protocol_version=protocol_version)

            listener = PacketListener(test_packet, serverbound.play.ChatPacket)

            packet = serverbound.play.ChatPacket(context).set_values(
                message=message)
            uncalled_packet = KeepAlivePacket().set_values(keep_alive_id=0)

            listener.call_packet(packet)
            listener.call_packet(uncalled_packet)


class PacketEnumTest(unittest.TestCase):
    def test_packet_str(self):
        class ExamplePacket(Packet):
            id = 0x00
            packet_name = 'example'
            definition = [
                {'alpha': VarInt},
                {'beta': VarInt},
                {'gamma': VarInt}]

            class Alpha(Enum):
                ZERO = 0

            class Beta(Enum):
                ONE = 1

        self.assertEqual(
            str(ExamplePacket(ConnectionContext(), alpha=0, beta=0, gamma=0)),
            '0x00 ExamplePacket(alpha=ZERO, beta=0, gamma=0)')


class TestReadWritePackets(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.context = ConnectionContext()
        self.context.protocol_version = SUPPORTED_PROTOCOL_VERSIONS[-1]

    def tearDown(self):
        del self.context

    def test_explosion_packet(self):
        Record = clientbound.play.ExplosionPacket.Record
        packet = clientbound.play.ExplosionPacket(
                    position=Vector(787, -37, 0), radius=15,
                    records=[Record(-14, -116, -5), Record(-77, 34, -36),
                             Record(-35, -127, 95), Record(11, 113, -8)],
                    player_motion=Vector(4, 5, 0))
        self._test_read_write_packet(packet)

    def test_combat_event_packet(self):
        packet = clientbound.play.CombatEventPacket()
        for event in (
            packet.EnterCombatEvent(),
            packet.EndCombatEvent(duration=415, entity_id=91063502),
            packet.EntityDeadEvent(player_id=178, entity_id=36, message='RIP'),
        ):
            packet.event = event
            self._test_read_write_packet(packet)

    def test_multi_block_change_packet(self):
        Record = clientbound.play.MultiBlockChangePacket.Record
        packet = clientbound.play.MultiBlockChangePacket(
                   chunk_x=167, chunk_z=15, records=[
                     Record(x=1, y=2, z=3, blockId=56, blockMeta=13),
                     Record(position=Vector(1, 2, 3), block_state_id=909),
                     Record(position=(1, 2, 3), blockStateId=909)])
        self.assertEqual(packet.records[0].blockId, 56)
        self.assertEqual(packet.records[0].blockMeta, 13)
        self.assertEqual(packet.records[0].blockStateId, 909)
        self.assertEqual(packet.records[0].position, Vector(1, 2, 3))
        self.assertEqual(packet.records[0], packet.records[1])
        self.assertEqual(packet.records[1], packet.records[2])
        self._test_read_write_packet(packet)

    def test_spawn_object_packet(self):
        EntityType = clientbound.play.SpawnObjectPacket.EntityType

        object_uuid = 'd9568851-85bc-4a10-8d6a-261d130626fa'
        pos_look = PositionAndLook(x=68.0, y=38.0, z=76.0, yaw=16, pitch=23)
        velocity = Vector(21, 55, 41)
        entity_id, type_name, type_id = 49846, 'EGG', EntityType.EGG

        packet = clientbound.play.SpawnObjectPacket(
                    x=pos_look.x, y=pos_look.y, z=pos_look.z,
                    yaw=pos_look.yaw, pitch=pos_look.pitch,
                    velocity_x=velocity.x, velocity_y=velocity.y,
                    velocity_z=velocity.z, object_uuid=object_uuid,
                    entity_id=entity_id, type_id=type_id, data=1)
        self.assertEqual(packet.position_and_look, pos_look)
        self.assertEqual(packet.position, pos_look.position)
        self.assertEqual(packet.velocity, velocity)
        self.assertEqual(packet.objectUUID, object_uuid)
        self.assertEqual(packet.type, type_name)

        packet2 = clientbound.play.SpawnObjectPacket(
                     position_and_look=pos_look, velocity=velocity,
                     type=type_name, object_uuid=object_uuid,
                     entity_id=entity_id, data=1)
        self.assertEqual(packet.__dict__, packet2.__dict__)

        packet2.position = pos_look.position
        self.assertEqual(packet.position, packet2.position)

        packet2.data = 0
        self._test_read_write_packet(packet)
        self._test_read_write_packet(packet2)

    def _test_read_write_packet(self, packet_in):
        packet_in.context = self.context
        packet_buffer = PacketBuffer()
        packet_in.write(packet_buffer)
        packet_buffer.reset_cursor()
        VarInt.read(packet_buffer)
        packet_id = VarInt.read(packet_buffer)
        self.assertEqual(packet_id, packet_in.id)

        packet_out = type(packet_in)(context=self.context)
        packet_out.read(packet_buffer)
        self.assertIs(type(packet_in), type(packet_out))
        self.assertEqual(packet_in.__dict__, packet_out.__dict__)
